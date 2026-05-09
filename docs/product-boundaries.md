# FoxSay Product Boundaries

## Core Promise
FoxSay is not a general-purpose assistant. It is a course-bound learning Copilot. The product should feel like a clever, slightly annoying fox that understands the current course better than the student, but it must never pretend to know material that was not provided.

## Course As Atomic Unit
- A course is the isolation boundary for materials, vector retrieval, graph construction, skeleton generation, chat, and review plans.
- Cross-course retrieval is forbidden unless a future product requirement explicitly introduces it.
- All backend contracts for materials, questions, answers, skeletons, review plans, and `/btw` interjections must include `course_id`.

## MVP Includes
- Importing a timetable from CSV/Excel to create course cards and exam countdowns.
- Manually creating a course.
- Uploading and registering materials such as PDF, PPT, images, and text notes.
- Asynchronous material processing into chunks, embeddings, graph facts, and course skeletons.
- Course-bound Q&A with CRAG policy and citations.
- Super exam mode with review plan generation, guided review, and `/btw` interjections.

## Explicitly Post-MVP
- Diagnostic 15-question flow.
- Exam paper generation.
- Course capsule sharing or community features.
- Multi-user accounts, permissions, and collaboration.
- Global calendar intelligence or a broad student cowork system.

## Product Voice
- Use concise, confident, fox-like copy.
- Refusals should be honest, not apologetic filler.
- Do not make the UI feel like a generic enterprise chatbot.

