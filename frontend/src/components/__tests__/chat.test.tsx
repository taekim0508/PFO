import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { readWriteups } from "@/lib/content";
import { toProjectView } from "@/lib/projectView";
import { PROJECTS } from "@/lib/projects";
import { AnswerText } from "../AnswerText";
import { IndexApp } from "../IndexApp";

const writeups = readWriteups();
const projects = PROJECTS.map((project) => toProjectView(project, writeups));

function app(fetchImpl: typeof fetch) {
  return render(<IndexApp hasResume={false} projects={projects} fetchImpl={fetchImpl} />);
}

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
    app(fetchImpl);

    await askThroughTheBox("Where did Tae go to school?");

    const [turn] = await screen.findAllByRole("listitem");
    expect(within(turn).getByText("Where did Tae go to school?")).toBeInTheDocument();
    await waitFor(() =>
      expect(turn).toHaveTextContent("Tae graduated from Vanderbilt in May 2026"),
    );
    expect(within(turn).getByRole("button", { name: "Source 1" })).toBeInTheDocument();
    expect(within(turn).getByLabelText("Suggested questions")).toBeInTheDocument();
  });

  it("asks a suggestion chip's question", async () => {
    const fetchImpl = answering([frame("done", DONE)]);
    app(fetchImpl);

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
    app(fetchImpl);

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
    app(fetchImpl);

    await askThroughTheBox("q");

    expect(await screen.findByRole("alert")).toHaveTextContent("Please wait a moment.");
  });

  it("calls a stream that closes without done or error cut off", async () => {
    const fetchImpl = answering([frame("delta", { text: "Tae interned as a" })]);
    app(fetchImpl);

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
    app(fetchImpl);

    await askThroughTheBox("A slow question");
    await act(async () => fireEvent.click(await screen.findByRole("button", { name: "Stop" })));

    expect(await screen.findByText("Stopped.")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Send question" })).toBeInTheDocument();
  });

  it("does not send an empty question", async () => {
    const fetchImpl = vi.fn();
    app(fetchImpl);

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

const ABROADLY_PASSAGE = {
  ...PASSAGE,
  label: 1,
  title: "Abroadly, Study Abroad Review Platform",
  heading_path: ["What I built and owned"],
  source_path: "abroadly.md",
  location: "Abroadly, Study Abroad Review Platform > What I built and owned",
  text: "## What I built and owned\n\nMy own features were peer messaging and bookmarking.",
};

function abroadlyAnswer() {
  return answering([
    frame("sources", { strategy: "dense", passages: [ABROADLY_PASSAGE, { ...PASSAGE, label: 2 }] }),
    frame("delta", { text: "Tae built messaging and bookmarking [1]." }),
    frame("done", { ...DONE, cited: [1] }),
  ]);
}

describe("projects, case studies, and sources", () => {
  it("shows every project, strongest first, without asking the model", async () => {
    const fetchImpl = vi.fn();
    app(fetchImpl);

    fireEvent.click(screen.getByRole("button", { name: "Explore my projects" }));

    const cards = within(await screen.findByLabelText("Related projects")).getAllByRole("button");
    expect(cards.map((c) => c.querySelector(".font-serif")?.textContent)).toEqual(
      projects.map((p) => p.name),
    );
    expect(fetchImpl).not.toHaveBeenCalled();
  });

  it("puts the cited project's card under the answer, with its follow-ups", async () => {
    app(abroadlyAnswer());

    await askThroughTheBox("What did Tae build at Abroadly?");

    const related = await screen.findByLabelText("Related projects");
    expect(within(related).getAllByRole("button")).toHaveLength(1);
    expect(related).toHaveTextContent("Abroadly");
    const abroadly = projects.find((p) => p.slug === "abroadly")!;
    expect(screen.getByLabelText("Suggested questions")).toHaveTextContent(abroadly.followUps[0]);
  });

  it("opens the case study from a card, closes it with Escape, and returns focus", async () => {
    app(vi.fn());
    fireEvent.click(screen.getByRole("button", { name: "Explore my projects" }));
    const card = within(await screen.findByLabelText("Related projects")).getAllByRole("button")[2];

    fireEvent.click(card);

    const panel = screen.getByRole("complementary", { name: "Abroadly" });
    expect(within(panel).getByRole("heading", { name: "Abroadly" })).toHaveFocus();
    expect(within(panel).getByText("Why magic links instead of passwords")).toBeInTheDocument();
    expect(panel).toHaveTextContent("Tae's contribution");

    fireEvent.keyDown(window, { key: "Escape" });

    expect(screen.queryByRole("complementary")).toBeNull();
    expect(card).toHaveFocus();
  });

  it("marks a heading the write-up does not cover as a placeholder", async () => {
    app(vi.fn());
    fireEvent.click(screen.getByRole("button", { name: "Explore my projects" }));
    const cards = within(await screen.findByLabelText("Related projects")).getAllByRole("button");

    fireEvent.click(cards[1]); // the chatbot: its write-up has no validation or results yet

    const panel = screen.getByRole("complementary");
    expect(within(panel).getAllByText("Placeholder").length).toBeGreaterThan(0);
  });

  it("opens the sources at the passage a citation points to", async () => {
    app(abroadlyAnswer());
    await askThroughTheBox("What did Tae build at Abroadly?");
    const toggle = await screen.findByRole("button", { name: /Sources · 2 passages/ });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    fireEvent.click(screen.getByRole("button", { name: "Source 1" }));

    expect(toggle).toHaveAttribute("aria-expanded", "true");
    const passage = document.querySelector('[data-label="1"]')!;
    expect(passage).toHaveTextContent("What I built and owned");
    expect(passage).toHaveTextContent("cited");
    expect(passage).toHaveTextContent("dense #1");
    expect(passage.className).toContain("bg-peach-tint");
  });
});

describe("related project cards", () => {
  it("show only projects the answer cited", async () => {
    const fetchImpl = answering([
      frame("sources", {
        strategy: "dense",
        passages: [
          ABROADLY_PASSAGE,
          { ...ABROADLY_PASSAGE, label: 2, source_path: "followthru.md" },
        ],
      }),
      frame("delta", { text: "Composite indexes [1]." }),
      frame("done", { ...DONE, cited: [1] }),
    ]);
    app(fetchImpl);

    await askThroughTheBox("How did Tae fix the slow query?");

    const related = await screen.findByLabelText("Related projects");
    expect(related).toHaveTextContent("Abroadly");
    expect(related).not.toHaveTextContent("FollowThru");
  });
});

describe("the case study on a phone", () => {
  it("takes the page behind it out of the tab order", async () => {
    const original = window.matchMedia;
    window.matchMedia = ((query: string) => ({
      matches: false,
      media: query,
      addEventListener: () => {},
      removeEventListener: () => {},
    })) as unknown as typeof window.matchMedia;
    try {
      app(vi.fn());
      fireEvent.click(screen.getByRole("button", { name: "Explore my projects" }));
      const card = within(await screen.findByLabelText("Related projects")).getAllByRole(
        "button",
      )[0];

      fireEvent.click(card);

      expect(card.closest("[inert]")).not.toBeNull();
      expect(screen.getByRole("banner")).toHaveAttribute("inert");
      fireEvent.keyDown(window, { key: "Escape" });
      expect(card.closest("[inert]")).toBeNull();
    } finally {
      window.matchMedia = original;
    }
  });
});
