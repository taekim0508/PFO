import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { AnswerText } from "../AnswerText";
import { IndexApp } from "../IndexApp";

const PASSAGE = {
  label: 1,
  title: "Education",
  heading_path: ["Degrees and dates"],
  source_path: "education.md",
  location: "Education > Degrees and dates",
  text: "I graduated from Vanderbilt University in May 2026.",
  score: 0.66,
  provenance: [{ strategy: "dense", rank: 1 }],
};
const DONE = {
  no_context: false,
  model: "fake",
  finish_reason: "stop",
  prompt_version: "v",
  cited: [1],
  invalid_citations: [],
  retrieval_ms: 10,
  first_text_ms: 20,
  total_ms: 30,
};

function frame(event: string, payload: unknown) {
  return `event: ${event}\ndata: ${JSON.stringify(payload)}\n\n`;
}

/** A fetch whose answer body is the given frames, delivered as one stream. */
function answering(frames: string[]) {
  return vi.fn().mockImplementation(
    async () =>
      new Response(
        new ReadableStream<Uint8Array>({
          start(controller) {
            for (const f of frames) controller.enqueue(new TextEncoder().encode(f));
            controller.close();
          },
        }),
      ),
  );
}

async function askThroughTheBox(question: string) {
  const user = userEvent.setup();
  await user.type(screen.getByLabelText("Ask about Tae's work"), `${question}{Enter}`);
}

describe("the chat", () => {
  it("streams an answer under the question and offers follow-ups", async () => {
    const fetchImpl = answering([
      frame("sources", { strategy: "dense", passages: [PASSAGE] }),
      frame("delta", { text: "Tae graduated from Vanderbilt " }),
      frame("delta", { text: "in May 2026 [1]." }),
      frame("done", DONE),
    ]);
    render(<IndexApp hasResume={false} fetchImpl={fetchImpl} />);

    await askThroughTheBox("Where did Tae go to school?");

    const turn = await screen.findByRole("listitem");
    expect(within(turn).getByText("Where did Tae go to school?")).toBeInTheDocument();
    await waitFor(() =>
      expect(turn).toHaveTextContent("Tae graduated from Vanderbilt in May 2026"),
    );
    expect(within(turn).getByRole("button", { name: "Source 1" })).toBeInTheDocument();
    expect(within(turn).getByLabelText("Suggested questions")).toBeInTheDocument();
  });

  it("asks a suggestion chip's question", async () => {
    const fetchImpl = answering([frame("done", DONE)]);
    render(<IndexApp hasResume={false} fetchImpl={fetchImpl} />);

    fireEvent.click(screen.getByRole("button", { name: "How I solve problems" }));

    await waitFor(() => expect(fetchImpl).toHaveBeenCalled());
    const body = JSON.parse(fetchImpl.mock.calls[0][1].body);
    expect(body.question).toBe("How does Tae approach solving problems?");
  });

  it("shows an error event's sentence and lets the visitor try again", async () => {
    const fetchImpl = answering([
      frame("sources", { strategy: "dense", passages: [] }),
      frame("error", { code: "model_unavailable", message: "The model isn't answering." }),
    ]);
    render(<IndexApp hasResume={false} fetchImpl={fetchImpl} />);

    await askThroughTheBox("Hello?");

    expect(await screen.findByRole("alert")).toHaveTextContent("The model isn't answering.");
    fireEvent.click(screen.getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(fetchImpl).toHaveBeenCalledTimes(2));
  });

  it("explains a rate limit instead of failing silently", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ error: { message: "Please wait a moment." } }), {
        status: 429,
      }),
    );
    render(<IndexApp hasResume={false} fetchImpl={fetchImpl} />);

    await askThroughTheBox("q");

    expect(await screen.findByRole("alert")).toHaveTextContent("Please wait a moment.");
  });

  it("calls a stream that closes without done or error cut off", async () => {
    const fetchImpl = answering([frame("delta", { text: "Tae interned as a" })]);
    render(<IndexApp hasResume={false} fetchImpl={fetchImpl} />);

    await askThroughTheBox("Where did he intern?");

    expect(await screen.findByRole("alert")).toHaveTextContent("cut off");
  });

  it("stops an answer with the Stop button", async () => {
    const fetchImpl = vi.fn().mockImplementation(
      (_url: string, init: RequestInit) =>
        new Promise((_resolve, reject) => {
          init.signal?.addEventListener("abort", () =>
            reject(new DOMException("aborted", "AbortError")),
          );
        }),
    );
    render(<IndexApp hasResume={false} fetchImpl={fetchImpl} />);

    await askThroughTheBox("A slow question");
    await act(async () => fireEvent.click(await screen.findByRole("button", { name: "Stop" })));

    expect(await screen.findByText("Stopped.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send question" })).toBeInTheDocument();
  });

  it("does not send an empty question", async () => {
    const fetchImpl = vi.fn();
    render(<IndexApp hasResume={false} fetchImpl={fetchImpl} />);

    await askThroughTheBox("   ");

    expect(fetchImpl).not.toHaveBeenCalled();
  });
});

describe("AnswerText", () => {
  it("renders paragraphs, lists, bold, and citations, and nothing as HTML", () => {
    const onCite = vi.fn();
    const { container } = render(
      <AnswerText
        text={
          "He built **two** things [1]:\n\n- messaging [2]\n- bookmarking\n\n<b>not html</b> [9]"
        }
        labels={[1, 2]}
        onCite={onCite}
      />,
    );

    expect(container.querySelectorAll("p")).toHaveLength(2);
    expect(container.querySelectorAll("li")).toHaveLength(2);
    expect(container.querySelector("strong")).toHaveTextContent("two");
    expect(container.querySelector("b")).toBeNull();
    expect(container).toHaveTextContent("<b>not html</b> [9]");
    fireEvent.click(screen.getByRole("button", { name: "Source 2" }));
    expect(onCite).toHaveBeenCalledWith(2);
    expect(screen.queryByRole("button", { name: "Source 9" })).toBeNull();
  });
});
