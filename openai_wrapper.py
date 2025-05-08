# chatgpt_wrapper.py
from __future__ import annotations

import base64
import os
import threading
import time
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Union

from openai import OpenAI
from openai.types.chat import ChatCompletion
from openai.types.responses import Response as ReasoningResponse

ModelName = str
UserContent = Union[str, Dict[str, Any], Sequence[Dict[str, Any]]]

rmdl = [
    "o1-2024-12-17",            # 15.0    60.0
    "o4-mini-2025-04-16",       #  1.1     4.4
    "o1",
    "o3",
]

smdl = [
    "gpt-4.1-2025-04-14",       #  2.0     8.0
    "gpt-4.1-mini-2025-04-14",  #  0.4     1.6
    "gpt-4o-2024-11-20",        #  2.5    10.0
    "gpt-4.1",
]

class ChatGPTWrapper:
    """
    Thread‑safe wrapper around the OpenAI SDK that supports:

    • Synchronous or non‑blocking calls (ready flag + wait helper)
    • Optional persistent history
    • Image and/or tool calling with a single entry point
    • Reasoning‑model and standard‑model routing
    • Running + per‑call token accounting
    """

    # ---- class‑wide model catalogues (each with vision capability) ---------

    REASONING_MODELS: set[ModelName] = {
        "o1-2024-12-17",            # 15.0    60.0
        "o4-mini-2025-04-16",       #  1.1     4.4
        "o1",
        "o3",
    }

    STANDARD_MODELS: set[ModelName] = {
        "gpt-4.1-2025-04-14",       #  2.0     8.0
        "gpt-4.1-mini-2025-04-14",  #  0.4     1.6
        "gpt-4o-2024-11-20",        #  2.5    10.0
        "gpt-4.1",
    }

    # ---- construction ------------------------------------------------------

    def __init__(
        self,
        *,
        default_model: ModelName = "gpt-4.1-2025-04-14",
        system_message: Optional[str] = None,
        developer_message: Optional[str] = None,
        chat_history: Optional[List[Dict[str, str]]] = None,
        persistent_chat: bool = False,
        hold_for_response: bool = True,
        default_tools: Optional[List[Dict[str, Any]]] = None,
        openai_client: Optional[OpenAI] = None,
        tool_executor = None,
        api_key = None
    ) -> None:
        """
        Parameters
        ----------
        system_message
            Required system role text shown to every request.
        default_model
            Fallback model if none supplied at call time.
        developer_message
            Optional persistent developer role message.
        chat_history
            Initial user/assistant message list; empty by default.
        persistent_chat
            If True, send entire history with each call; else send only current turn.
        hold_for_response
            If False, calls return immediately; ready flag is set when done.
        default_tools
            If provided, used when a call requests `tools=True`.
        openai_client
            Advanced: supply a pre‑configured OpenAI() instance.
        """
        self.client = openai_client or OpenAI(api_key = api_key)

        self.system_message = (
            {"role": "system", "content": system_message}
            if system_message
            else None
        )
        self.developer_message = (
            {"role": "developer", "content": developer_message}
            if developer_message
            else None
        )

        self.persistent_chat = persistent_chat
        self.hold_for_response = hold_for_response
        self.default_model = default_model
        self.default_tools = default_tools or []

        self.history: List[Dict[str, str]] = chat_history.copy() if chat_history else []
        self._ready = threading.Event()
        self._lock = threading.Lock()
        self._last_response: Optional[Union[ChatCompletion, ReasoningResponse]] = None

        self._response_history = []
        self.tool_executor = tool_executor

        # token accounting
        self.token_totals = {"input_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0, "total_tokens": 0}
        self.token_log: List[Dict[str, int]] = []

    # -----------------------------------------------------------------------
    # public helpers
    # -----------------------------------------------------------------------

    @property
    def ready(self) -> bool:
        """Non‑blocking flag set True once the most recent request is finished."""
        return self._ready.is_set()

    def wait_until_ready(self, timeout: Optional[float] = None) -> bool:
        """
        Block until the current request finishes or *timeout* seconds elapse.
        Returns True if ready, False on timeout.
        """
        return self._ready.wait(timeout=timeout)

    @property
    def last_response(self) -> Union[ChatCompletion, ReasoningResponse, None]:
        """Return the completed response object (or None before first call)."""
        return self._last_response

    # -----------------------------------------------------------------------
    # single unified call entry point
    # -----------------------------------------------------------------------

    def __call__(
        self,
        user_content: UserContent,
        *,
        model: Optional[ModelName] = None,
        images: Optional[Sequence[Union[str, Path]]] = None,
        tools: Union[bool, Sequence[Dict[str, Any]], None] = None,
        reasoning: Optional[Dict[str, Any]] = None,
        text: Optional[Dict[str, Any]] = None,
        stream: bool = False,
        **kwargs: Any,
    ) -> Optional[Union[ChatCompletion, ReasoningResponse]]:
        """
        Send a request to the OpenAI API.

        Parameters
        ----------
        user_content
            Either a plain string **or** a messages‑style list/tuple of dicts.
        model
            Override default model.
        images
            Optional iterable of file paths (str or Path) to include.
        tools
            • True  -> use wrapper's *default_tools*
            • list  -> use provided tool spec
            • None  -> no tools (normal chat)
        reasoning
            Dict of reasoning‑specific kwargs, e.g. {"effort": "medium"}.
            Ignored for standard models.
        stream
            Whether to request streaming responses (standard models only).
        **kwargs
            Any extra parameters forwarded to the chat or responses endpoint.

        Returns
        -------
        Response object *or* None if `hold_for_response=False`
        and you choose not to block until completion.
        """
        # Prepare messages for this call ------------------------------------
        model = model or self.default_model
        is_reasoning = model in self.REASONING_MODELS

        user_messages = self._normalize_user_content(user_content)
        if images:
            user_messages[-1]['content'] = [{"type": "input_text", "text": user_messages[-1]['content']}]
            user_messages[-1]["content"].extend(
                [self._image_part(path) for path in images]
            )

        messages = []
        if self.system_message:
            messages.append(self.system_message)
        if self.developer_message:
            messages.append(self.developer_message)
        if self.persistent_chat:
            messages.extend(self.history)
        messages.extend(user_messages)

        # Build payload common parts ---------------------------------------
        common_payload: Dict[str, Any] = {
            "model": model,
            "input": messages, #if is_reasoning else None,  # reasoning uses 'input'
            # "messages": messages if not is_reasoning else None,
            **kwargs,
        }

        # tools logic
        if tools is True:
            common_payload["tools"] = self.default_tools
            common_payload["tool_choice"] = "auto"
        elif tools:
            common_payload["tools"] = tools
            common_payload["tool_choice"] = "required"

        if is_reasoning:
          if reasoning:
            common_payload["reasoning"] = reasoning
          else:
            common_payload["reasoning"] = {"effort": "medium"}

        if text:
            common_payload["text"] = text

        # Submit request ----------------------------------------------------
        self._ready.clear()
        if self.hold_for_response:
            # blocking
            response = self._dispatch(common_payload, is_reasoning, stream=stream)
            self._postprocess(response, user_messages)
            self._ready.set()
            return response
        else:
            # non‑blocking: run in worker thread
            threading.Thread(
                target=self._background_task,
                args=(common_payload, is_reasoning, user_messages, stream),
                daemon=True,
            ).start()
            return None  # caller will use wait_until_ready / last_response

    # -----------------------------------------------------------------------
    # internal helpers
    # -----------------------------------------------------------------------

    def _background_task(
        self,
        payload: Dict[str, Any],
        is_reasoning: bool,
        user_messages: List[Dict[str, Any]],
        stream: bool,
    ) -> None:
        """Worker thread for non‑blocking operations."""
        response = self._dispatch(payload, is_reasoning, stream=stream)
        with self._lock:
            self._postprocess(response, user_messages)
            self._ready.set()

    # ------ api dispatch ---------------------------------------------------

    def _dispatch(
        self,
        payload: Dict[str, Any],
        is_reasoning: bool,
        stream: bool = False,
    ) -> Union[ChatCompletion, ReasoningResponse]:
        """Route to the appropriate OpenAI endpoint."""
        # try:
        if is_reasoning:
            # Remove None 'messages' key; 'input' is already set.
            # payload["stream"] = stream
            payload.pop("messages", None)
            return self.client.responses.create(**payload)  # type: ignore[arg-type]
        else:
            # Remove None 'input' key; 'messages' is already set.
            # This path is deprecated and can be removed safely
            payload.pop("messages", None)

            return self.client.responses.create(**payload)
            # payload.pop("input", None)
            # payload["stream"] = stream
            # return self.client.chat.completions.create(**payload)  # type: ignore[arg-type]
        # except Exception as e:
        #     print(e)
        #     self._ready.set()
        #     raise e

    # ------ utilities ------------------------------------------------------

    @staticmethod
    def _image_part(path: Union[str, Path]) -> Dict[str, str]:
        """Return a message content part dict for an embedded local image."""
        path = Path(path).expanduser().resolve()
        mimetype = _infer_mimetype(path)
        with open(path, "rb") as fp:
            b64 = base64.b64encode(fp.read()).decode("ascii")
        return {"type": "input_image", "image_url": f"data:{mimetype};base64,{b64}"}

    @staticmethod
    def _normalize_user_content(user_content: UserContent) -> List[Dict[str, Any]]:
        """Ensure user_content is in unified messages format."""
        if isinstance(user_content, (list, tuple)):
            # assume already message dicts
            return [dict(msg) for msg in user_content]  # shallow copy
        if isinstance(user_content, dict):
            return [user_content]
        # simple string
        return [{"role": "user", "content": user_content}]

    def _postprocess(
        self,
        response: Union[ChatCompletion, ReasoningResponse],
        user_messages: List[Dict[str, Any]],
    ) -> None:
        """Update history + token accounting after a completed call."""
        # token logging
        usage: Dict[str, int] = dict(response.usage)  # type: ignore[arg-type]
        self.token_log.append(usage)
        for k in ("input_tokens", "output_tokens", "reasoning_tokens", "total_tokens"):
            self.token_totals[k] += usage.get(k, 0)

        # history update (assistant role content may differ in reasoning)
        assistant_msg = self._assistant_message_from_response(response)
        if True: # self.persistent_chat:
            self.history.extend(user_messages)
            self.history.extend(assistant_msg)
            self._response_history += [response]
        self._last_response = response

    @staticmethod
    def _assistant_message_from_response(
        response: Union[ChatCompletion, ReasoningResponse],
        tool_executor = None
    ) -> Dict[str, str]:
        """Extract assistant reply content in messages‑compatible form."""
        if isinstance(response, ChatCompletion):
            return {
                "role": response.choices[0].message.role,
                "content": response.choices[0].message.content,
            }
        # response API (visible output tokens are in response.output)
        # visible = next( (item for item in response.output if (item.role == "assistant" if hasattr(item, "role") else False)  ), None )
        visible = response.output_text
        if visible == "":
            visible = []
            for tool_call in response.output:
              if tool_call.type != "function_call":
                  continue
              # visible.append(dict(tool_call))
              # visible.append(tool_call)
              name = tool_call.name
              args = json.loads(tool_call.arguments)
              if tool_executor:
                  visible.append({"role": "assistant", "content": str(dict(tool_call))})
                  result = tool_executor(name, args)
                  result_dict = {
                      "type": "function_call_output",
                      "name": name,
                      "args": args,
                      "call_id": tool_call.call_id,
                      "output": str(result)
                  }
                  visible.append({"role": "assistant", "content": str(result_dict)})
              else:
                  visible.append({"role": "assistant", "content": f"Function Call\nFunction: {name}\nArguments: {args}"})
            return visible
        #return {"role": visible.role, "content": visible.content}
        return [{"role": "assistant", "content": visible}]

    # ------------------------------------------------------------------ repr

    def __repr__(self) -> str:
        cls = self.__class__.__name__
        status = "ready" if self.ready else "busy"
        return f"<{cls} model={self.default_model!r} calls={len(self.token_log)} status={status}>"

    # ------------------------------------------------------------------ eof


# ---------------------------------------------------------------------------
# helper functions (module‑level)
# ---------------------------------------------------------------------------


def _infer_mimetype(path: Path) -> str:
    """Very small helper for mime‑type guessing—extend as needed."""
    ext = path.suffix.lower().lstrip(".")
    return {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "gif": "image/gif",
        "webp": "image/webp",
    }.get(ext, "application/octet-stream")
