OceanAI - Jr. GenAI Engineer Campus Recruitment
GenAI Assignment - The Agent That Builds Agents

Overview

Build ForgeAI: a system that takes a one-paragraph brief (“I need an assistant that answers HR
policy questions for shore staff”) plus a folder of documents, and autonomously produces a
working, tested agent - system prompt, retrieval configuration, tool selection, output contract, and
an auto-generated evaluation set - then improves its own output until the evals pass or a budget runs
out.

You are not building a chatbot. You are building the machine that builds the chatbot, tests it like a QA
engineer, and ships it with evidence. At the review we bring a brief and a document folder you have
never seen; ForgeAI runs unattended and must hand back a working agent and an honest quality
report.

The difficulty is orchestration under uncertainty: every stage runs on a small, imperfect open model,
and the system as a whole must still be trustworthy.

Scenario

Our production platform lets admins configure agents by hand - prompt, knowledge bases, tools. The
next step is an admin who writes only one paragraph. ForgeAI sits in between: it interviews the
requester, drafts the agent, generates the tests, judges the results, diagnoses the failures, and
applies targeted fixes - the loop a good GenAI engineer runs by hand, automated.

This is prompt engineering at one remove: your prompts write prompts, and your evals must be good
enough to judge an agent you did not hand-craft. The candidates who do well here are the ones who
distrust their own pipeline and build the checks that catch it lying to them.

Core requirements

All nine are mandatory. The theme: the factory must work on briefs you never saw while building
it.

1.

Intake interviewer. Reads the brief, inspects the document folder, asks the requester at most 5
clarifying questions (a CLI dialogue is fine), and writes a structured requirements document:
scope, audience, tone, must-answer topics, must-refuse topics.

2. Groundability guard. If the brief asks for things the documents cannot support, the factory flags
it at the requirements stage - it must not generate an agent that will hallucinate the gap away.

3. Agent generator. From requirements plus documents, produce a complete declarative agent

definition: system prompt, chunking and retrieval parameters, tool selection from your registry (it
must attach only the tools the brief actually needs), and an output contract.

OceanAI  ·  Campus Recruitment

Page 1

4. Eval generator. Auto-create a test set from the documents themselves: at least 20 cases

spanning answerable questions (each with expected grounding: source document plus key
facts), out-of-scope questions that must be refused, and edge cases (ambiguous phrasing,
answers spanning two documents). The set must be generated, not hand-written - commit the
generation prompts.

5.

Judge. Automated scoring per case: grounded? correct against the expected facts? refused
when it should? LLM-as-judge with a local model is fine, but defend it against its known failure
modes (position bias, self-preference, verbosity bias) - or combine it with deterministic checks.

6. Critic–optimizer loop. Run evals -> classify every failure into a category (retrieval miss / prompt
defect / hallucination / wrong refusal) -> apply a targeted fix, not a full regeneration -> re-run.
Maximum 3 iterations. Every change is logged: what changed, why, which failures it addressed,
score before and after.

7. Honest reporting. Final output: the agent definition, the per-iteration scorecard, and a report
that states what still fails and why. A factory that claims 100% is suspicious; a factory that
explains its 78% is hired.

8. Runnable product. The generated agent must actually run: a minimal generic chat runner (CLI

or simple UI) that loads any produced definition.

9.

Two full demonstrations. Run the factory end to end on two very different briefs and document
sets, and commit the complete artifacts of both runs: requirements, definitions, generated eval
sets, iteration logs, scorecards.

Data & assets

l Two demo runs, committed in full. Pick two deliberately different briefs and document sets - for

example an HR policy assistant over two or three HR policy PDFs, and a ship-spares
procurement assistant over a catalogue CSV plus supplier PDFs. Public documents or
LLM-synthesized ones are both fine; commit the synthesis prompts.

l Tool registry. Give the factory 3–4 tools to choose from: a CSV lookup, a calculator, a keyless

public HTTP API (e.g. open-meteo), current date. Part of the test is that the factory attaches only
what a brief needs - an HR agent with a weather tool is a factory defect.

l The produced artifacts of both runs - requirements documents, agent definitions, generated eval
sets, iteration logs, scorecards - are the main evidence the factory works. Commit all of them.

l At the review: an unseen brief and document folder, run unattended in front of us. Build for that,

not for your two demos.

Stretch goals (optional)

Attempt these only after all nine core requirements work; each earns bonus credit.

l Prompt tournament: the generator proposes two or three candidate system prompts; the eval set

picks the winner, with the comparison in the report

l Budget enforcement: a token/latency budget per run with early stopping when an iteration stops

paying for itself

OceanAI  ·  Campus Recruitment

Page 2

l Human checkpoint: the requester approves or edits the requirements document before

generation proceeds

l Factory vs human baseline: hand-write one of the two demo agents yourself and show, with

evals, where the factory beats you and where it loses

l Regression mode: documents change -> re-run the old eval set against the regenerated agent

and report what broke

l UI and hosting: a simple web UI (Streamlit/Gradio) for the factory and the chat runner, and

hosting the app on any free tier (Hugging Face Spaces, Streamlit Community Cloud, Render) -
both are add-ons that earn bonus credit

AI tools: You are free to use any AI tools to complete the assignment - there are no restrictions as
such. Use your creativity and out-of-the-box thinking.

Note: Do not copy this assignment or share your work with other candidates. If similar submissions
are found, all of them will be rejected.

OceanAI  ·  Campus Recruitment

Page 3


