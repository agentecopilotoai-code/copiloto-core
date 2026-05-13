// Single mutable widget state container. Kept dumb on purpose so the UI module
// and the poller can both reach into it without circular imports.

export function createState() {
  return {
    open: false,
    sending: false,
    started: false,
    sessionToken: null,
    conversationId: null,
    contactId: null,
  };
}
