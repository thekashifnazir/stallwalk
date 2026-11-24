# Voice embed notes (checked 24 Nov 2026)

Source: elevenlabs.io/docs/eleven-agents/customization/widget

- Inline or non-floating widget: **not documented** as an HTML attribute. Only `variant="expanded"` (plus `dismissible="true"`) is shown; `placement` and `"variant": "full"` exist only in the agent config JSON (`platform_settings.widget`), not on the tag.
- Starting a call from our own button: **no documented widget JS API**. The only documented event is `elevenlabs-convai:call` (for client tools). The docs point to the SDKs for custom control.
- So for our own button, use the documented JS client, not the widget:

```html
<script type="module">
  import { Conversation } from "https://cdn.jsdelivr.net/npm/@elevenlabs/client@1.35.0/+esm";
  let convo;
  document.querySelector(".btn-voice").onclick = async () => {
    await navigator.mediaDevices.getUserMedia({ audio: true });
    convo = await Conversation.startSession({ agentId: "AGENT_ID", connectionType: "webrtc",
      onMessage: (m) => console.log(m.source, m.message) });
  };
</script>
```

Fallback if the client fails: keep `<elevenlabs-convai agent-id="..." variant="expanded">` on the page and have `.btn-voice` scroll to it. Check the `startSession` option names against the client README for the pinned version.
