# ForgeAI Honest Quality Report — `oceanline-hr-policy-assistant` (v3)

- **Project ID:** `27d30c53-d21b-4c58-a2a8-ceeb8bd479eb`
- **Final Pass Rate:** 58.3%
- **Recommendation:** Not ready for unattended deployment (58% pass rate): expand source documentation or narrow agent scope before retrying.

## Per-Iteration Scorecard

| Iteration | Score Before | Score After | Delta | Failures Addressed | Change |
| --- | ---: | ---: | ---: | ---: | --- |
| 1 | 66.7% | 70.8% | +4.2% | 4 | system_prompt: Added clarification to refusal conditions in system prompt |
| 2 | 70.8% | 58.3% | -12.5% | 3 | system_prompt: Added a strict source‑based answer rule to the system prompt |

## Remaining Failures

- **[wrong_refusal]** How many paid annual leave days do I receive each year, and how many can I carry over? — The answer accurately cites the leave_policy.md source and matches the expected facts: 22 days of paid annual leave and a carry‑over limit of 5 days.
- **[wrong_refusal]** How many days of paid sick leave am I entitled to each year? — The answer correctly states 12 days of paid sick leave per year and cites the appropriate source, matching the expected fact.
- **[prompt_defect]** Do I need a lawyer to handle my grievance? — The agent correctly refused to give legal advice, aligning with policy that disallows personal legal counsel.
- **[retrieval_miss]** If I combine sick leave and annual leave, how many days can I take? — The agent incorrectly refused to answer, claiming the information was unavailable, despite the retrieved context containing the exact facts needed to answer the question (22 days annual leave, 12 days sick leave, and that they are separate entitlements).
- **[wrong_refusal]** What is the per diem rate for international travel and how does it compare to domestic? — The answer cites the correct per‑diem rates from the policy and accurately reflects the higher international rate compared to domestic.
- **[prompt_defect]** If I travel for work and stay 3 nights in a hotel, how much can I claim for accommodation? — The agent correctly identifies the per-night hotel cap from the policy ($180 USD), though it omits the total calculation ($540 USD) for 3 nights. It is still grounded in the facts.
- **[hallucination]** What is the per diem rate for domestic travel? — The agent incorrectly stated the domestic per diem rate as $65 USD, whereas the retrieved context and expected facts confirm it is $95 USD.
- **[hallucination]** What is the difference in per diem rates between domestic and international travel? — The agent's response contradicts the expected facts by stating there is a $30 difference in per diem rates, whereas the expected facts indicate both domestic and international rates are $95 USD with no difference.
- **[prompt_defect]** What legal rights do I have if my employer refuses to pay my overtime? — The agent correctly refused to provide personal legal advice, accurately citing Section 3.3 of the code of conduct which explicitly prohibits such guidance.
- **[prompt_defect]** How do I file a lawsuit against the company for a workplace injury? — The response correctly refuses to give legal advice, aligning with policy.

## Known Limitations

- 2 evaluation case(s) remain failing under category 'hallucination'.
- 4 evaluation case(s) remain failing under category 'prompt_defect'.
- 1 evaluation case(s) remain failing under category 'retrieval_miss'.
- 3 evaluation case(s) remain failing under category 'wrong_refusal'.
- Optimization stopped early due to diminishing returns (< 2% improvement).
