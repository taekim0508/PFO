---
title: Abroadly, Study Abroad Review Platform
---

## The problem Abroadly solves

Students researching study-abroad programs run into information that's scattered across brochures, social media, and informal conversations, and none of it reliably answers the questions students actually have: how difficult the courses are, what the program-provided housing is actually like, what things really cost, and where to eat or spend a weekend once you're there. I led a four-person team building Abroadly, a platform that consolidates that experience into three connected areas, programs, local places, and trips, built around reviews written by other students instead of promotional material.

## What I built and owned

We built Abroadly from August to December 2025, over four sprints, and shipped it to 20 classmates and Vanderbilt's study abroad office. On the four-person team, I scoped sprint work, assigned feature ownership, paired with teammates on implementation, and reviewed their pull requests. My own features were peer messaging and bookmarking. Messaging let a student contact the person who wrote a review, with the message linked back to the specific program, place, or trip it was about: I built its eight authenticated FastAPI endpoints and the React inbox, with checks that only the sender or recipient can read a message, replies linked to the message they answer, and read and unread state that persists. Bookmarking let students save programs, places, and trips across ten REST endpoints. I also collaborated with my teammates on the shared 13-table schema connecting users, reviews, bookmarks, and messages. The backend is FastAPI with SQLModel and SQLAlchemy over PostgreSQL in production (SQLite locally for development), with Alembic handling migrations, deployed on Railway. The frontend is React and TypeScript, deployed on Vercel. Authentication uses email magic links and JWT sessions instead of passwords.

## Why programs, places, and trips are separate data models

One modeling decision I stand behind is treating programs, places, and trips as separate domain models instead of one generic reviewable-content type. A generic model would have meant less repeated code, but it also would have produced a lot of nullable fields and weaker validation, since a program has a cost and duration that a restaurant recommendation doesn't, and a trip has a destination and trip type that a course review doesn't. Keeping them separate meant more repeated CRUD, review, and bookmark logic across the three domains, which is a real cost, but it made each type's fields and validation rules explicit instead of generic. If the product grew, I'd keep the separate domain models but extract shared service-layer patterns for review creation, rating aggregation, and bookmarking, so the repetition goes away without losing the domain clarity.

## Separating program housing from independent housing

A related decision was keeping program-provided housing and independent housing as different concepts instead of one housing table. Program housing belongs to a specific study-abroad program and answers "what is this program's housing actually like." Independent housing is modeled as a place with a housing category, and answers a different question entirely, "where should I live in this city." Forcing both into one ambiguous table would have meant a schema that couldn't cleanly represent either question. Splitting them meant the review flow could ask the right question for each case instead of one generic housing review that didn't quite fit either situation.

## Fixing a slow filtered-search query

One of the concrete engineering problems I worked through was a slow filtered listing query. The search used a wildcard ILIKE pattern, and I found that pattern couldn't use a standard B-tree index at all, so every search was scanning far more rows than it needed to. I profiled the query plans with EXPLAIN to confirm that diagnosis, then added composite indexes that matched the actual filter and sort pattern being used, which cut that listing query from 9.2 milliseconds to 0.47 milliseconds. I also tuned connection pool sizing and timeouts to handle concurrent load better, since the default pool settings weren't built with multiple simultaneous users in mind.

## Preventing duplicate bookmarks under concurrent requests

The bookmark endpoints check whether a student has already saved an item before saving it, but that check alone isn't enough: two requests arriving at nearly the same moment, from a double click or a retried network call, can both pass the check before either one has written anything. So each of the three bookmark tables also has a compound unique constraint on the student and the saved item, which makes the database itself refuse the second insert. When that happens, the endpoint catches the integrity error and rolls back the transaction instead of failing with an error, so the student ends up with exactly one bookmark either way.

## Building the CI pipeline

I also built the project's continuous delivery pipeline: 365 automated tests total, 99 with pytest on the backend and 266 with Jest and React Testing Library on the frontend, with coverage thresholds checked in CI. The backend and frontend suites ran as separate GitHub Actions jobs on every push and pull request to main, so every change showed whether both suites passed and coverage held at the threshold we'd set for the project.

## Why magic links instead of passwords

For authentication, I chose email magic links and JWT sessions instead of a traditional password system. The benefit was real: no password database to secure, no password-reset flow to build and maintain, and less friction for students signing in. The cost is that it makes the system dependent on email delivery actually working, introduces cross-origin cookie complexity between the frontend and backend, and means a student can't sign in at all if email delivery is down. For a student-facing tool used for planning rather than something time-critical, I judged that tradeoff to be worth it, but it's not a decision I'd make the same way for every product.

## A sprint scope disagreement with a teammate

During one of our early sprints, we'd committed to building the program and review flow, where students could explore study-abroad programs and leave reviews. While we were working on it, a teammate wanted to start integrating direct messaging at the same time, reasoning that if a student found a review helpful, we'd eventually want them to message that reviewer directly, so we might as well connect the two systems while we were already in the review code. I disagreed, since messaging wasn't part of what we'd committed to that sprint and I was worried about adding complexity before the core flow was done. I recognized we disagreed but didn't push to resolve it explicitly as a team early enough, so we kept building with different ideas of what the sprint actually included, took on too much, and missed the deadline we'd set.

Afterward, instead of treating it as a right-or-wrong technical call, I sat down with my teammate to understand his reasoning, and it held up: if reviews were eventually going to lead into conversations, building them together could avoid redundant work later. The real problem wasn't that either of us had a bad idea, it was that we didn't have a process for resolving that kind of tradeoff before we started building. After that, we started every sprint by explicitly agreeing on scope and what success looked like, and if someone found something that would materially change scope mid-sprint, we brought it back to the group before building it rather than deciding unilaterally. That experience made me a lot more deliberate about surfacing disagreements early and understanding what someone else is optimizing for before assuming their approach is wrong.

## Revisiting the project for this review

Putting this file together, I went back to the public demo version of this project, which is a stripped-down copy of what we actually shipped, and it's currently stale since I don't have its database running. That review surfaced things worth being upfront about: N+1 query patterns in places I hadn't optimized (the review-count and rating aggregation on programs, places, and trips each do one query per item instead of a single grouped query), incomplete Alembic migrations alongside leftover automatic table creation that could let a database drift from what the migrations describe, and write endpoints that check whether a user is logged in but not whether they actually own the resource they're editing. None of that is how the project ran when we delivered it, and the indexing and CI work described above did ship, but revisiting older code and finding real gaps like this is exactly the kind of review I'd want to build into the actual delivered version if I picked this project back up.
