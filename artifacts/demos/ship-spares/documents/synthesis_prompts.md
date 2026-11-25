# Document Synthesis Prompts — Demo 2 (Ship-Spares Procurement)

The three procurement assets in `documents/` combine tabular CSV inventory with textual supplier and customs policies:
1. `spares_catalogue.csv`: 10 marine spare parts with `part_number`, `description`, `system`, `unit_price_usd`, `stock_on_hand`, `min_reorder_level`, `lead_time_days`, and `supplier_code`.
2. `supplier_terms.md`: MOQ rules, bulk discount tiers (5% for >=10 units, 10% for >=25 units), expedite surcharge (+18%), and payment terms (Net 45).
3. `customs_freight_guide.md`: Port customs clearance lead times (3 days Singapore, 5 days Rotterdam), 7.5% CIF marine spares duty, and $420 flat air-freight fee for emergency AOG/vessel-immobilized orders.

