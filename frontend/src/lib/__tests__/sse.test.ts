import { describe, expect, it } from "vitest";
import { createSseParser, type SseEvent } from "../sse";

function parse(chunks: string[]) {
  const events: SseEvent[] = [];
  const parser = createSseParser((event) => events.push(event));
  for (const chunk of chunks) parser.push(chunk);
  parser.end();
  return events;
}

const STREAM =
  'event: sources\ndata: {"passages":[]}\n\n' +
  'event: delta\ndata: {"text":"Tae "}\n\n' +
  'event: delta\ndata: {"text":"studied."}\n\n' +
  'event: done\ndata: {"cited":[1]}\n\n';

const EXPECTED = [
  { event: "sources", data: '{"passages":[]}' },
  { event: "delta", data: '{"text":"Tae "}' },
  { event: "delta", data: '{"text":"studied."}' },
  { event: "done", data: '{"cited":[1]}' },
];

describe("createSseParser", () => {
  it("parses whole events", () => {
    expect(parse([STREAM])).toEqual(EXPECTED);
  });

  it("gives the same events however the stream is split", () => {
    for (const size of [1, 2, 3, 7, 13]) {
      const chunks = [];
      for (let i = 0; i < STREAM.length; i += size) chunks.push(STREAM.slice(i, i + size));
      expect(parse(chunks)).toEqual(EXPECTED);
    }
  });

  it("accepts \\r\\n and \\r line endings, even split between chunks", () => {
    const crlf = STREAM.replaceAll("\n", "\r\n");
    expect(parse([crlf])).toEqual(EXPECTED);
    expect(parse(crlf.split(/(?<=\r)/))).toEqual(EXPECTED);
    expect(parse([STREAM.replaceAll("\n", "\r")])).toEqual(EXPECTED);
  });

  it("joins multiple data lines with newlines", () => {
    expect(parse(["data: one\ndata: two\n\n"])).toEqual([{ event: "message", data: "one\ntwo" }]);
  });

  it("ignores comments and fields it does not use", () => {
    expect(parse([": keep-alive\nid: 7\nretry: 100\nevent: delta\ndata: x\n\n"])).toEqual([
      { event: "delta", data: "x" },
    ]);
  });

  it("keeps a space that is part of the value", () => {
    expect(parse(["data:  two spaces\n\n"])).toEqual([{ event: "message", data: " two spaces" }]);
  });

  it("emits a last event that has no blank line after it", () => {
    expect(parse(["event: done\ndata: {}"])).toEqual([{ event: "done", data: "{}" }]);
  });

  it("emits nothing for a block without data", () => {
    expect(parse(["event: delta\n\n"])).toEqual([]);
  });
});
