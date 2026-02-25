# Grid Operations Persona-Responsibility Matrix

> **Source references** (shown in left sidebar of original):
> - [ScienceDirect – Renewable and Sustainable Energy Reviews](https://www.sciencedirect.com/science/article/pii/S1364032121005396)
> - Federation of American Scientists – *Unlocking AI's Grid Modernization Potential*
> - SYSO Technologies – *Day-Ahead Markets: Strategic Energy*
> - National Academy of Sciences – *Evolving Planning Criteria for a Sustainable Power Grid* (July 2024)
> - PubMed Central – *Critical Risk Indicators (CRIs) for the Electric Grid*
> - Wikipedia – *Power System Operations and Control*
> - Advanced Distribution Management Systems (NLR, Siemens Corp., Corporate Technology, Columbia University, Holy Cross Energy, Siemens Digital Grid)
> - Utility Asset Management & Day Ahead/Real Time Energy Markets references

---

## Time Horizons Overview

| Time Horizon | Cadence | Description |
|---|---|---|
| **Rolling Strategic and Seasonal Planning** | Months to years, revisited weekly–daily | Defines long-term and seasonal operating posture, resource adequacy, major projects, and risk/resilience criteria in studies that are updated and referenced on an ongoing basis throughout the year. |
| **Day-Ahead and Week-Ahead Operations Setup** | D-7 to D-1, tied to markets and schedules | Translates strategic posture into concrete limits, outage windows, and resource commitments for the coming days, combining engineering studies, market/scheduling outcomes, and operational risk decisions. |
| **Intra-Day Readiness and Continuous Rebalancing** | Pre-shift and whenever things change | Reconciles plans with live conditions at the start of each shift and whenever forecasts, outages, or system status change, adjusting work, limits, and priorities to keep the system and crews aligned. |
| **Real-Time Operations and Minor Event Handling** | Core shift, seconds to hours | Covers the main control-room window where operators monitor the grid, execute switching, respond to small disturbances, and continuously track risk and resilience indicators under normal conditions. |
| **Local Outage and Abnormal-Condition Response** | Episodic overlays on real time | Represents focused response "modes" for non-major outages and abnormal configurations that sit on top of normal operations, often with multiple overlapping episodes per day requiring targeted coordination. |
| **Shift Handover, Review, and Continuous Model/Data Updates** | Episodic overlays on real time | Represents focused response "modes" for non-major outages and abnormal configurations that sit on top of normal operations, often with multiple overlapping episodes per day requiring targeted coordination. |

---

## Persona Responsibilities by Time Horizon

### 1. Transmission System Operator (TSO)

| Time Horizon | Responsibilities |
|---|---|
| **Rolling Strategic & Seasonal** | Review seasonal operating guides and constraint lists; provide feedback on historical operational challenges and near-misses through established review processes to support future revisions. |
| **Day-Ahead & Week-Ahead** | Review day-ahead outage and constraint sets; verify that planned switching is operationally feasible; flag complex or high-risk switching sequences to Transmission Ops Manager and TSO Planner for risk acceptance. |
| **Intra-Day Readiness** | Perform pre-shift checks on EMS/SCADA health, alarms, and topology; ensure clear understanding of today's key outages, constraints, and expectations at T-D interfaces. |
| **Real-Time Operations** | Coordinate with DSO Operator to monitor transmission conditions, flows, voltages, and margins; execute approved switching; respond to alarms; adjust setpoints based on updated conditions. |
| **Local Outage & Abnormal** | Handle minor contingencies (equipment trips, small load/generation changes); coordinate with DSO Operator on interface-related issues; implement temporary configurations and interface-related topology changes. |
| **Shift Handover & Review** | Complete detailed shift logs, including actions taken, alarms, overrides, and deviations; highlight operational pain points and system issues; participate in shift handover discussions and debriefs with planners and managers; clarify issues for follow-up. |

---

### 2. Transmission System Planner

| Time Horizon | Responsibilities |
|---|---|
| **Rolling Strategic & Seasonal** | Develop and maintain seasonal and longer-term studies for transfer capability, voltage stability, and associated constraints; integrate planned projects, interconnection queues, and policy changes into planning assumptions. |
| **Day-Ahead & Week-Ahead** | Run day-ahead and short-term contingency studies including planned outages and forecasted conditions; generate instructions for the coming days; provide operators and managers with clear limits, schedules, and constraint lists. |
| **Intra-Day Readiness** | Perform updated studies when outages, system conditions, or schedules change within the day; advise on risk and feasibility as conditions evolve. |
| **Real-Time Operations** | Issue updated constraints or temporary instructions to TSO Operator and Transmission Ops Manager; support operators in analyzing unusual behavior, providing technical recommendations that inform but do not replace operational decisions. |
| **Local Outage & Abnormal** | Document model discrepancies or data issues revealed in real-time to feed into model improvement efforts; evaluate the risk of proposed abnormal configurations or emergent outages, quantifying margins and contingency exposure. |
| **Shift Handover & Review** | Advise the Transmission Ops Manager on risk trade-offs for continuing planned work; review daily logs and events and guide prioritization of studies that address recurring operational issues; communicate planning insights to managers and DSO Planner to align long-term and daily operations. |

---

### 3. Transmission Operations Manager

| Time Horizon | Responsibilities |
|---|---|
| **Rolling Strategic & Seasonal** | Define reliability and risk posture targets for transmission operations and review seasonal guides; coordinate with planners, DSO leadership, and executives on major risk themes and long-term mitigation plans. |
| **Day-Ahead & Week-Ahead** | Approve complex outage and switching plans, balancing reliability, project delivery, and market or contractual considerations; communicate upcoming high-risk periods and constraints to internal stakeholders. |
| **Intra-Day Readiness** | Confirm that staffing, skills, tools, and procedures are adequate for the day's risk profile and planned work; re-prioritize work or adjust risk posture when intra-day changes occur (e.g., additional outages, forecast changes). |
| **Real-Time Operations** | Oversee operator performance and adherence to procedures during "blue sky" operations and minor events; decide on escalation level and whether to adjust system posture or request additional resources. |
| **Local Outage & Abnormal** | Coordinate with internal leadership, utilities, markets, and regulators when local issues have broader implications; lead or sponsor debriefs identifying near-misses and systemic issues. |
| **Shift Handover & Review** | Lead or sponsor debrief sessions; communicate performance stories to executives; identify near-misses and technology-driven improvement opportunities. |

---

### 4. Distribution System Operator (DSO Operator)

| Time Horizon | Responsibilities |
|---|---|
| **Rolling Strategic & Seasonal** | Provide feedback on chronic problem feeders, devices, and DER behavior through established reliability reporting processes for planners, IT/OT, and asset management to address. |
| **Day-Ahead & Week-Ahead** | Identify areas where visibility or DER control gaps impede daily operations; review planned feeder switching, maintenance, and work; check feasibility with forecasted load and DER injections. |
| **Intra-Day Readiness** | Highlight conflicts or scheduling issues; at shift start, review today's switching, planned work, and anticipated DER/load profiles; validate OMS/ADMS health. |
| **Real-Time Operations** | Adjust operational expectations when unplanned jobs or conditions change; monitor feeder status and voltages; perform routine switching and reconfiguration to manage load and voltage; update status in operational tools. |
| **Local Outage & Abnormal** | Handle minor interruptions and faults using standard procedures; dispatch crews via work systems; coordinate with Distribution Ops Manager, Maintenance Engineer, and TSO Operator on interface-related issues. |
| **Shift Handover & Review** | Validate that network models match actual configuration at end of shift; correct discrepancies where found; document device, configuration, and process issues and share them as inputs to planning and asset management. |

---

### 5. DSO Planner

| Time Horizon | Responsibilities |
|---|---|
| **Rolling Strategic & Seasonal** | Perform feeder and station studies for capacity, reliability, and DER hosting; propose reconfiguration and investment options; align distribution planning assumptions with transmission constraints, asset strategies, and resilience goals. |
| **Day-Ahead & Week-Ahead** | Design day-/week-ahead switching and reconfiguration plans incorporating planned work and forecasted conditions; validate that plans respect T-D interface limits and local operational constraints; issue clear instructions to DSO Operators and managers. |
| **Intra-Day Readiness** | Analyze intra-day change requests (new work, constraints) and update switching plans or sequencing as needed; coordinate with TSO Planner to ensure interface-related changes are consistently modeled and communicated. |
| **Real-Time Operations** | Support DSO Operators in understanding unusual loadings or DER behavior, using quick-turn analysis and advisory recommendations that inform but do not replace operational decisions; identify recurring operational patterns that signal planning or asset issues and record them for follow-up studies. |
| **Local Outage & Abnormal** | Evaluate alternate feeder configurations for restoration and maintenance during abnormal conditions; advise Distribution Ops Manager on trade-offs and medium-term fixes (e.g., sectionalizing, protection adjustments). |
| **Shift Handover & Review** | Analyze outage and event data for planning-relevant trends (weak spots, DER impacts); update planning models and candidate project lists; communicate insights to Distribution Ops Manager and TSO Planner. |

---

### 6. DSO Manager

| Time Horizon | Responsibilities |
|---|---|
| **Rolling Strategic & Seasonal** | Set distribution reliability and safety targets; identify priority feeders and areas; work with DSO Planner and Asset Manager to ensure operational priorities and constraints are clearly reflected in project and asset portfolios developed by planning and asset management. |
| **Day-Ahead & Week-Ahead** | Approve distribution work schedules and major switching sequences affecting customers or high-risk areas; balance resources, reliability, and customer impacts across the upcoming week. |
| **Intra-Day Readiness** | Confirm control-room and field readiness; review emergent work and unplanned outages; set priorities and deferrals; clarify escalation thresholds and communication expectations for the shift. |
| **Real-Time Operations** | Oversee operator response to minor outages and power-quality issues; ensure adherence to standards; re-allocate crews and work if the operational workload or risk moves outside expectations. |
| **Local Outage & Abnormal** | Approve restoration strategies and higher-risk switching steps in abnormal conditions; manage communication with internal leadership and customer-facing groups on outage extent and progress. |
| **Shift Handover & Review** | Lead daily operations review on reliability, safety, and customer impact; log improvement items and training needs; provide operational input into asset, planning, and modernization initiatives based on recent performance. |

---

### 7. Asset Manager

| Time Horizon | Responsibilities |
|---|---|
| **Rolling Strategic & Seasonal** | Maintain asset registry with condition, criticality, and risk scores; update strategies per asset class; build long-term asset investment portfolios aligning with reliability and resilience objectives. |
| **Day-Ahead & Week-Ahead** | Recommend which high-risk or high-impact asset interventions should be prioritized for near-term scheduling to operations and maintenance, ensuring they align with outage plans and system constraints; provide asset-criticality context for proposed work to operations and maintenance engineering. |
| **Intra-Day Readiness** | Provide asset-criticality context when changes occur and propose adjustments to maintenance priorities; ensure critical assets' work is being appropriately scheduled. |
| **Real-Time Operations** | Consume near-real-time asset performance signals (e.g., breaker operations, transformer loading) into condition models; flag assets showing abnormal behavior for accelerated inspection or strategy updates. |
| **Local Outage & Abnormal** | Interpret event causes and device behavior to determine whether an event indicates degradation or design issues; recommend follow-up inspections or accelerated replacements; advise operations on asset-aware restoration considerations. |
| **Shift Handover & Review** | Integrate outage, work, and performance data into health models and risk rankings; recommend follow-up actions; communicate asset performance trends to planning and operations. |

---

### 8. Maintenance Engineer

| Time Horizon | Responsibilities |
|---|---|
| **Rolling Strategic & Seasonal** | Define maintenance strategies (preventive/predictive) and standard tasks for each asset class based on failure modes and OEM guidance; work with Asset Manager to ensure maintenance aligns with risk and lifecycle goals. |
| **Day-Ahead & Week-Ahead** | Translate prioritized asset work into detailed task plans, required skills, durations, and resource estimates in coordination with work management and scheduling teams; support scheduling by indicating which tasks can be grouped and what outage durations are needed. |
| **Intra-Day Readiness** | Confirm that crews, tools, and access conditions are ready for today's work; adjust task sequencing if operations or weather change; advise operators and managers on what maintenance can safely proceed given current system conditions. |
| **Real-Time Operations** | Provide operations with clarity on whether to continue operation, derate, or request removal from service; provide quick technical guidance on temporary fixes or work-arounds that can be used until full maintenance can be scheduled. |
| **Local Outage & Abnormal** | Analyze the technical implications of faults and abnormal operations on specific assets; recommend immediate inspection or testing steps; design follow-up maintenance tasks and inspection plans triggered by particular event types or signatures. |
| **Shift Handover & Review** | Review maintenance outcomes, failures, and repeat work to refine task definitions, intervals, and procedures; work with Asset Manager to feed maintenance performance into asset health models and future strategies. |

---

### 9. IT/OT Systems & Data Operations

| Time Horizon | Responsibilities |
|---|---|
| **Rolling Strategic & Seasonal** | Plan capacity, redundancy, and monitoring strategy for SCADA/EMS/DMS/OMS systems; set data/system reliability targets and reviews; align future system needs with planning and project roadmaps. |
| **Day-Ahead & Week-Ahead** | Set data/system reliability targets and configurations for key operations; prepare and test failover and backup configurations for key operations; schedule non-critical grid work for system/data readiness. |
| **Intra-Day Readiness** | Prepare and test communications and integrations; create connectivity for critical work; report status to ops leadership. |
| **Real-Time Operations** | Monitor for anomalies and open tickets for issues needing attention; monitor system performance and data quality; respond to incidents affecting operator visibility or control. |
| **Local Outage & Abnormal** | Provide work-arounds or alternative views to operations and outage/work teams; prioritize system stability and data integrity during abnormal grid conditions; defer non-essential IT/OT work; coordinate with security/vendors if indicated. |
| **Shift Handover & Review** | Support operations with additional visibility or ad-hoc data when standard views are stressed; review daily incident logs and performance metrics; tune monitoring and dashboards; update knowledge base and runbooks; provide a daily IT/OT status and risk summary to operations managers. |

---

## Key Structural Observations

1. **Progressive time resolution**: Responsibilities flow from strategic (months-to-years) through real-time (seconds-to-hours), with each persona's scope narrowing as urgency increases.

2. **Transmission vs. Distribution hierarchy**: The matrix distinguishes between Transmission-level roles (TSO, Transmission System Planner, Transmission Operations Manager) and Distribution-level roles (DSO Operator, DSO Planner, DSO Manager), reflecting the physical and organizational separation in grid operations.

3. **Support functions span all horizons**: Asset Manager, Maintenance Engineer, and IT/OT Systems & Data Operations serve as cross-cutting support functions that interface with both transmission and distribution operational roles across all time horizons.

4. **Escalation pathways**: The matrix implicitly defines escalation chains — operators execute, planners advise, managers approve — with the pattern consistent across both transmission and distribution domains.

5. **Interface management**: Multiple cells reference T-D (Transmission-Distribution) interface coordination, highlighting this as a critical operational boundary requiring explicit attention across personas and time horizons.
