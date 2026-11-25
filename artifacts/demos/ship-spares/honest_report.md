# ForgeAI Honest Quality Report — `marine-engineering-procurement-assistant` (v2)

- **Project ID:** `3bac4fb3-c3ad-4d1b-83ff-a905b8921bba`
- **Final Pass Rate:** 29.2%
- **Recommendation:** Not ready for unattended deployment (29% pass rate): expand source documentation or narrow agent scope before retrying.

## Per-Iteration Scorecard

| Iteration | Score Before | Score After | Delta | Failures Addressed | Change |
| --- | ---: | ---: | ---: | ---: | --- |
| 1 | 37.5% | 29.2% | -8.3% | 7 | system_prompt: Refine refusal conditions to exclude permissible political content |

## Remaining Failures

- **[retrieval_miss]** What is the unit price and stock on hand for part ME-4012? — The agent incorrectly refused to answer, claiming the part ME-4012 was not in the context, despite the expected facts indicating it should be answerable with a unit price of $480.00 and stock of 4.
- **[retrieval_miss]** If I order 12 units of part AE-2104, what bulk discount applies and what is the discounted unit price? — The agent correctly identified the 5% bulk discount from supplier_terms.md but failed to provide the discounted unit price of $902.50 for part AE-2104, which is required by the expected facts. The retrieved context chunks did not include the specific row for AE-2104 from spares_catalogue.csv, leading to a retrieval miss.
- **[wrong_refusal]** How many business days does customs clearance take at Rotterdam? — The answer cites the correct 5 business days for Rotterdam from the provided customs_freight_guide.md chunk and matches the expected fact.
- **[wrong_refusal]** What is the lead time for part PU-1145 and what is the expedited lead time if needed? — The answer correctly states the 18‑day lead time and 9‑day expedited time, citing the appropriate CSV and markdown sources, matching the expected facts.
- **[wrong_refusal]** What is the minimum reorder level for part HV-8040? — The answer cites the correct source and matches the expected fact of 8.
- **[wrong_refusal]** If I order 30 units of part BO-5010, what is the total landed cost including customs duty and freight? — The answer correctly cites the 10% bulk discount, 7.5% customs duty, and $150 freight from the provided documents and notes the missing unit price, staying factual and grounded.
- **[retrieval_miss]** How many days will it take to clear customs and receive part NV-7011 if shipped from Singapore? — The agent correctly identified the 3-day customs clearance time but failed to include the 15-day lead time for part NV-7011, which is explicitly stated in the retrieved context (Chunk 5) and required by the expected facts.
- **[prompt_defect]** Can you give me medical advice on treating a broken arm? — The agent correctly refused to provide medical advice, consistent with its role and without fabricating facts.
- **[prompt_defect]** What system does part ME-4012 belong to and what is its supplier code? — The agent correctly identified that part ME-4012 belongs to the Main Propulsion system and has the supplier code SUP-WARTSILA, which is directly supported by Chunk 4 from spares_catalogue.csv.
- **[prompt_defect]** What are the standard payment terms specified in the supplier documentation? — The agent correctly identified the standard payment terms as Net 45 days from the bill of lading, which is explicitly stated in the retrieved context (supplier_terms.md, Section 1.3).
- **[prompt_defect]** What is the customs duty percentage applicable to marine spares? — Answer correctly states 7.5% duty, citing the customs_freight_guide.md source.
- **[wrong_refusal]** What bulk discount tier applies if an engineer orders exactly 10 units of a spare part? — The answer correctly states a 5% discount for 10 units, matching the supplier_terms.md source that specifies 10–24 units qualify for 5%.
- **[prompt_defect]** How many total marine spare parts and assets are covered in the tabular CSV inventory catalogue? — The agent correctly identified that there are 10 marine spare parts in the tabular CSV inventory catalogue, which is directly supported by the retrieved context from 'spares_catalogue.csv' and 'synthesis_prompts.md'.
- **[prompt_defect]** Can you recommend a diet plan to help me lose weight while onboard the vessel? — The assistant correctly refused to provide a diet plan, which is outside its scope of marine procurement.
- **[prompt_defect]** What is the total customs clearance time and port customs lead time if clearing cargo in Singapore compared to Rotterdam? — The agent correctly identified the customs clearance lead times for Singapore (3 days) and Rotterdam (5 days) based on the provided context, accurately answering the user's question.
- **[prompt_defect]** If an order qualifies for the maximum bulk discount tier, what percentage discount is applied and what is the expedite surcharge if expedited shipping is also required? — The agent correctly identified the 10% bulk discount for orders of 25 or more units and the 18% expedite surcharge, both of which are explicitly stated in the retrieved context from supplier_terms.md and synthesis_prompts.md.
- **[wrong_refusal]** Considering that marine spares incur a 7.5% CIF duty, what rule determines when the $420 flat air-freight fee applies to an order? — The answer correctly states that the $420 flat air‑freight fee applies to emergency air‑freight for vessel‑immobilized (critical) spares, matching the expected fact and the retrieved context.

## Known Limitations

- 8 evaluation case(s) remain failing under category 'prompt_defect'.
- 3 evaluation case(s) remain failing under category 'retrieval_miss'.
- 6 evaluation case(s) remain failing under category 'wrong_refusal'.
- Optimization stopped early due to diminishing returns (< 2% improvement).
