/**
 * The projects the site shows as cards and case studies, strongest first.
 *
 * Every line here is drawn from Tae's own write-ups in content/; nothing is added. The
 * case-study sections do not restate those write-ups: they name which of a file's own
 * sections belong under each heading, and the page shows that text. An empty list means the
 * write-up says nothing for that heading, and the page shows a marked placeholder rather
 * than filler. A heading that does not exist in the file fails the build (see the test).
 *
 * Review this file whenever a write-up changes.
 */

export type CaseStudyKey =
  "problem" | "contribution" | "architecture" | "decisions" | "validation" | "results";

export const CASE_STUDY_HEADINGS: Record<CaseStudyKey, string> = {
  problem: "Problem",
  contribution: "Tae's contribution",
  architecture: "Architecture",
  decisions: "Key decisions and tradeoffs",
  validation: "Validation",
  results: "Results",
};

export type Project = {
  slug: string;
  /** The write-up in content/ this project comes from. */
  file: string;
  name: string;
  /** Where and when, as a small label. */
  context: string;
  /** One line: the problem it solves. */
  problem: string;
  /** Tae's part, kept separate from the team's. */
  role: string;
  tags: string[];
  /** For each case-study heading, the write-up's own section headings to show under it. */
  caseStudy: Record<CaseStudyKey, string[]>;
  /** Full questions, since each question is answered on its own. */
  followUps: string[];
};

export const PROJECTS: Project[] = [
  {
    slug: "ambassador-matching",
    file: "ai-producer-ambassador-matching-pipeline.md",
    name: "Ambassador Matching Pipeline",
    context: "AI Producer · Software engineer intern · Jun to Sep 2025",
    problem:
      "Matching Gen Z students with the AI ambassadors best suited to mentor them, from asymmetric, free-text profiles.",
    role: "Built the matching prototype end to end, and authored the API spec and data models the team built against.",
    tags: ["Python", "Pydantic", "NumPy", "BM25", "Reciprocal rank fusion", "gpt-4o-mini"],
    caseStudy: {
      problem: ["The problem: matching Gen Z students with AI ambassadors"],
      contribution: [
        "The API and data model the team built against",
        "Handling the ambiguity of a startup internship with no clearly defined path",
        "Details about the internship I don't have on record",
      ],
      architecture: [
        "What the prototype was built with",
        "The six-stage pipeline",
        "How retrieval narrows the candidate pool before any model call",
        "The data model: keeping current, target, and transitions separate",
      ],
      decisions: [
        "Why the system decides matches instead of just recommending options",
        "Resolving ambiguous language into a fixed taxonomy",
        "What I decided was allowed to influence a match",
        "Making the matches explainable, not just plausible",
      ],
      validation: ["Debugging retrieval that looked plausible but wasn't right"],
      results: ["What I validated, and what I'd have done next"],
    },
    followUps: [
      "How did Tae debug the matching pipeline's retrieval?",
      "Why does Tae's matching system decide matches instead of recommending options?",
      "What did Tae decide the matcher was not allowed to use?",
    ],
  },
  {
    slug: "portfolio-chatbot",
    file: "personal-portfolio-chatbot.md",
    name: "Portfolio Chatbot",
    context: "This site · Second version · 2026",
    problem:
      "A resume or a static page is shallow; this lets recruiters ask questions answered only from Tae's own writing.",
    role: "Building it himself: retrieval, generation on open-weight models, and this site.",
    tags: ["FastAPI", "PostgreSQL", "pgvector", "Hybrid retrieval", "Open-weight models"],
    caseStudy: {
      problem: ["The problem this project solves"],
      contribution: [],
      architecture: [
        "What I'm building, and what's actually running today",
        "The first version, and how it differs from this one",
      ],
      decisions: [
        "Why I chose open-weight models and hybrid retrieval",
        "Open engineering decisions I'm still working through",
      ],
      validation: [],
      results: [],
    },
    followUps: [
      "Why does this chatbot use open-weight models?",
      "How is this chatbot different from the first version?",
      "How does this chatbot find the right passages?",
    ],
  },
  {
    slug: "abroadly",
    file: "abroadly.md",
    name: "Abroadly",
    context: "Vanderbilt · Four-person team, led by Tae · Aug to Dec 2025",
    problem:
      "Study-abroad information is scattered; Abroadly gathers student reviews of programs, places, and trips in one place.",
    role: "Led the team and scoped sprints; built peer messaging and bookmarking.",
    tags: ["FastAPI", "SQLModel", "PostgreSQL", "React", "TypeScript", "GitHub Actions"],
    caseStudy: {
      problem: ["The problem Abroadly solves"],
      contribution: ["What I built and owned", "A sprint scope disagreement with a teammate"],
      architecture: [
        "Why programs, places, and trips are separate data models",
        "Separating program housing from independent housing",
      ],
      decisions: [
        "Why magic links instead of passwords",
        "Preventing duplicate bookmarks under concurrent requests",
      ],
      validation: ["Building the CI pipeline"],
      results: ["Fixing a slow filtered-search query", "Revisiting the project for this review"],
    },
    followUps: [
      "How did Tae fix the slow search query on Abroadly?",
      "How did Abroadly prevent duplicate bookmarks?",
      "What did Tae learn from the sprint disagreement on Abroadly?",
    ],
  },
  {
    slug: "followthru",
    file: "followthru.md",
    name: "FollowThru",
    context: "iOS app · Three-person team, led by Tae · Jan to Jun 2026",
    problem:
      "Turning a broad intention into a concrete, trackable habit, with an AI coach and social accountability.",
    role: "Led the team; built the backend, the AI habit-coaching chat, the cloud deployment, and most of the iOS client.",
    tags: ["Swift", "SwiftUI", "FastAPI", "OpenAI API", "AWS EC2", "GitHub Actions"],
    caseStudy: {
      problem: ["The problem FollowThru solves"],
      contribution: ["What I built: the stack and the contract between app and backend"],
      architecture: ["How I deployed the backend"],
      decisions: [
        "Making a multi-turn LLM conversation reliable",
        "Separating extraction from generation with prompt chaining",
        "Keeping context across stateless model calls",
      ],
      validation: ["Testing"],
      results: [],
    },
    followUps: [
      "How did Tae make FollowThru's AI chat reliable?",
      "How did Tae deploy the FollowThru backend?",
      "What would Tae improve first in FollowThru?",
    ],
  },
  {
    slug: "traffic-controller",
    file: "xcps-lab-research.md",
    name: "Explainable Traffic Signal Controller",
    context: "Explainable Cyber-Physical Systems Lab, Vanderbilt · Jan to Jun 2026",
    problem:
      "Controlling a simulated traffic light so that every decision can be explained, and the explanation checked, afterward.",
    role: "Research assistant; his own project, built to learn explainability in cyber-physical systems.",
    tags: ["SUMO", "TraCI", "Q-learning", "Docker"],
    caseStudy: {
      problem: ["What I built: an explainable traffic signal controller"],
      contribution: ["My role in the lab"],
      architecture: ["Three controllers under the same rules"],
      decisions: ["Making the explanations faithful, not just plausible"],
      validation: ["Reproducibility"],
      results: ["Results", "Limitations"],
    },
    followUps: [
      "Which traffic controller performed best in Tae's research?",
      "How does Tae check that the traffic controller's explanations are faithful?",
      "What are the limitations of Tae's traffic research?",
    ],
  },
];

export function projectForFile(file: string): Project | undefined {
  return PROJECTS.find((project) => project.file === file);
}
