/**
 * An incremental Server-Sent Events parser.
 *
 * Network chunks do not respect event boundaries: one chunk can hold half an event, or
 * three and a half. `push` takes whatever text arrived, emits every event that is now
 * complete, and keeps the rest until more arrives. An event is complete at a blank line.
 * Lines are split on \n, \r\n, or \r, as the SSE standard allows.
 */

export type SseEvent = { event: string; data: string };

export function createSseParser(onEvent: (event: SseEvent) => void) {
  let buffer = "";
  let name = "";
  let data: string[] = [];
  // Whether the last chunk ended in "\r". If the next one starts with "\n", the two are
  // one "\r\n" line ending split across chunks, not two line endings.
  let endedWithCr = false;

  function dispatch() {
    if (data.length > 0) {
      onEvent({ event: name || "message", data: data.join("\n") });
    }
    name = "";
    data = [];
  }

  function line(text: string) {
    if (text === "") {
      dispatch();
      return;
    }
    if (text.startsWith(":")) return; // a comment, used as a keep-alive
    const colon = text.indexOf(":");
    const field = colon === -1 ? text : text.slice(0, colon);
    let value = colon === -1 ? "" : text.slice(colon + 1);
    if (value.startsWith(" ")) value = value.slice(1);
    if (field === "event") name = value;
    else if (field === "data") data.push(value);
    // id and retry are not used by this API.
  }

  return {
    push(chunk: string) {
      if (endedWithCr && chunk.startsWith("\n")) chunk = chunk.slice(1);
      if (chunk === "") return;
      endedWithCr = chunk.endsWith("\r");
      buffer += chunk;
      const lines = buffer.split(/\r\n|\r|\n/);
      buffer = lines.pop() ?? "";
      for (const text of lines) line(text);
    },
    /** The stream closed. A final event with no blank line after it still counts. */
    end() {
      if (buffer) line(buffer);
      buffer = "";
      dispatch();
    },
  };
}
