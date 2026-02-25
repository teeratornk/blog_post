# Customer Journey for a Hurricane Extreme Weather Event

> **Source references** (shown in left sidebar of original):
> - US Hurricane Preparedness: 5 Steps to Effectively Manage Hurricane Season
> - Effective Hurricane Planning: Essential Strategies
> - Strengthening Critical Infrastructure Resilience
> - Phases of Cyber Incident Response
> - Strategies for Successful Storm Mitigation
> - EPA Hurricane Preparedness Guide
> - ABM Guide / Playbook references
> - FEMA / Infrastructure resilience materials

---

## Event Phases Overview

| Phase | Timeframe | Description |
|---|---|---|
| **Seasonal Readiness and Asset Inventory & Risk Profiling** | Months to Weeks Before Season | Teams work across offices, data centers, and some field locations. Their focus is on compiling accurate asset databases and creating risk profiles that will guide all future preparedness efforts. Efforts are often collaborative but can be slowed by data inconsistencies or resource constraints. |
| **Pre-Storm Forecasting, Predictive Modeling & Scenario Simulation** | 14 Days to 72 hours before landfall | Operations and emergency management centers begin to see real-time weather data. Analysts run models forecasting probable impact zones and damage, while planners refine crew mobilization strategies. This phase is marked by increased activity and a shared sense of anticipation as uncertainty narrows. |
| **Immediate Pre-Storm Mobilization** | 72–0 hours before landfall | Command centers and field staging areas become hubs of rapid action. Teams finalize staffing and equipment deployments while communicating closely. The window for decision-making tightens rapidly, and the pressure to get asset protection and resource readiness right is intense. |
| **Storm Impact & Real-Time Monitoring & Response** | 0–48 hours Post Landfall | Emergency Operations Centers, system control rooms, and field crews operate under stressful, often hazardous conditions. Communication lines may be compromised, and data may be delayed or incomplete, complicating urgent decision-making. The primary goal is safety and prioritized restoration. |
| **Restoration & Post Event Continuous Improvement** | 48 hours to 30 Days Post Landfall | Recovery offices and remote field locations coordinate ongoing repairs, system validation, and customer communication efforts. Teams reflect on what worked and what didn't and begin documenting lessons to improve future resilience, often balancing operational exhaustion with commitment to long-term improvement. |

---

## Persona Responsibilities by Phase

### 1. Asset Management

| Phase | Responsibilities |
|---|---|
| **Seasonal Readiness** | Update asset registry with condition scores. Run seasonal vulnerability models. Validate GIS mapping accuracy. Perform risk-based asset prioritization. |
| **Pre-Storm Forecasting** | Run damage/outage probability models. Coordinate with grid operations. Refine risk prioritization and scenarios. Sync with emergency management planning. |
| **Immediate Pre-Storm** | Schedule high-priority maintenance. Confirm field crew and resource readiness. Monitor progress of urgent repairs. |
| **Storm Impact** | Monitor asset conditions via sensor data and field reports. Adjust restoration priorities dynamically. |
| **Restoration** | Communicate updates to operations. Analyze restoration and damage data. Update asset health models. |
| **Post Event** | Recommend resilience improvements. Update asset models with hurricane damage data. |

---

### 2. Maintenance Engineer

| Phase | Responsibilities |
|---|---|
| **Seasonal Readiness** | Inspect critical assets and staging areas. Validate equipment readiness and spares. Conduct safety and storm-hardening training. |
| **Pre-Storm Forecasting** | Finalize crew assignments based on forecast. Prepare repair materials. Coordinate with dispatch. |
| **Immediate Pre-Storm** | Mobilize crews to staging. Conduct pre-shift safety briefings. |
| **Storm Impact** | Lead damage assessment and prioritized repair. Report status and hazards. Maintain crew safety. |
| **Restoration** | Document work completed. Update asset records. |
| **Post Event** | Debrief with operations for lessons learned. |

---

### 3. Emergency Manager / Incident Commander

| Phase | Responsibilities |
|---|---|
| **Seasonal Readiness** | Update emergency protocols. Validate mutual aid agreements. Conduct multi-agency drills. |
| **Pre-Storm Forecasting** | Activate EOC. Coordinate forecast information dissemination. Communicate readiness status to responders. |
| **Immediate Pre-Storm** | Mobilize emergency crews and resources. Manage logistics and safety plans. |
| **Storm Impact** | Lead multi-agency coordination. Address safety incidents. |
| **Restoration** | Deliver public communications. Update emergency response plans. Conduct after-action reviews. |
| **Post Event** | Enhance training and preparedness. |

---

### 4. Field Operations Supervisor / Crew Lead

| Phase | Responsibilities |
|---|---|
| **Seasonal Readiness** | Inspect critical assets and staging areas. Validate equipment readiness and spares. Conduct safety and storm-hardening training. |
| **Pre-Storm Forecasting** | Finalize crew assignments based on forecast. Prepare repair materials. Coordinate with dispatch. |
| **Immediate Pre-Storm** | Mobilize crews to staging. Conduct pre-shift safety briefings. |
| **Storm Impact** | Lead damage assessment and prioritized repair. Report status and hazards. Maintain crew safety. |
| **Restoration** | Document work completed. Update asset records. |
| **Post Event** | Debrief with operations for lessons learned. Develop data-driven improvement plans. |

---

### 5. IT/OT Systems and Data Analytics Manager

| Phase | Responsibilities |
|---|---|
| **Seasonal Readiness** | Validate SCADA/OMS/DMS integration. Conduct system reliability and failover tests. Scale infrastructure for peak demand. Perform OT vulnerability scans and patch validation. Backup configurations. Test incident response runbooks and drills with operations. |
| **Pre-Storm Forecasting** | Support predictive model deployment. Assure data quality and flow. |
| **Immediate Pre-Storm** | Ensure system uptime during peak demand. Manage cybersecurity threats. Staff 24/7 coverage. Validate cybersecurity procedures. |
| **Storm Impact** | Provide situational awareness dashboards. Support incident reporting systems. Monitor for cyber anomalies masked by storm noise. Advise manual overrides if compromise suspected. Coordinate secure vendor access. |
| **Restoration** | Analyze post-event data. Support incident reporting. Manage emergency privileged account access. Update playbooks and hardening measures. |
| **Post Event** | Develop improvement plans. Feed cyber requirements into resilience investments. |

---

### 6. Cybersecurity / OT Security Officer

| Phase | Responsibilities |
|---|---|
| **Seasonal Readiness** | Conduct phishing simulation and tabletop drills. Harden OT vulnerability scans and patch systems. Test incident response runbooks. Lock down remote access configurations. |
| **Pre-Storm Forecasting** | Increase SIEM monitoring and threat hunting. Coordinate cyber escalation paths with EOC/Grid Ops. Verify secure remote operations connectivity. |
| **Immediate Pre-Storm** | Validate secure failover/manual procedures. Elevate SIEM/intrusion detection monitoring. Staff 24/7 cybersecurity coverage. Block non-essential external access. |
| **Storm Impact** | Monitor for cyber anomalies masked by storm noise. Detect suspected access compromise. Secure vendor privileged account access. Monitor for ransomware spikes. |
| **Restoration** | Coordinate emergency access measures. Update playbooks and hardening. Analyze phishing/ransomware attempts. |
| **Post Event** | Conduct post-event cyber review (attempts, near-misses). Feed findings into resilience investments. |

---

### 7. Transmission System Operator (TSO)

*Named persona: Rocky John*

| Phase | Responsibilities |
|---|---|
| **Seasonal Readiness** | Identify hurricane-high-risk corridors for structural integrity. Run hurricane wind-impact simulations using historical storm data. Adjust planning assumptions for predicted hurricane paths. Validate vegetation clearance for hurricane wind zones. Harden infrastructure (guy wires, tower bracing, insulator checks). Reprioritize reinforcement projects for critical corridors. |
| **Pre-Storm Forecasting** | Expedite pre-event upgrades (storm hardening). Coordinate with RTOs on load-shedding strategies. Align inter-regional contingency protocols. Confirm switching readiness for critical corridors and high-voltage lines. |
| **Immediate Pre-Storm** | Activate transmission emergency control protocols. Confirm switching readiness for critical corridors. Validate emergency procurement and resource allocation. Mobilize crews and mutual aid. |
| **Storm Impact** | Monitor real-time voltage and frequency. Execute rapid isolation of damaged segments under hurricane conditions. Coordinate with regional operators. Support restoration prioritization for transmission-induced faults. |
| **Restoration** | Conduct forensic analysis of tower failures and line coverage losses. Validate temporary configurations. Update damage data. Support restoration sequencing. |
| **Post Event** | Update hurricane resilience standards and frameworks. Recommend relocation of flood-prone substations. Document regulatory compliance. Recommend elevated hardened hurricane mitigation. |

---

### 8. Transmission Planner

*Named persona: Rocky John*

| Phase | Responsibilities |
|---|---|
| **Seasonal Readiness** | Develop outage/restoration playbooks. Validate switching sequences for contingencies. Train control room staff on emergency protocols. Identify critical transmission paths. |
| **Pre-Storm Forecasting** | Assess restoration scenarios. Finalize restoration sequencing plans. Coordinate with emergency management. |
| **Immediate Pre-Storm** | Oversee crew and equipment staging. Finalize switching plans. Prepare control room for event operations. |
| **Storm Impact** | Direct grid switching. Manage fault isolations and service restoration. |
| **Restoration** | Verify restoration completeness. Report operational performance metrics. Coordinate with field crews and EOC. |
| **Post Event** | Plan system improvements. Update operational plans. |

---

### 9. Transmission Operations Manager

*Named persona: Rocky John*

| Phase | Responsibilities |
|---|---|
| **Seasonal Readiness** | Develop outage/restoration playbooks. Validate switching sequences for contingencies. Train control room staff on emergency protocols. |
| **Pre-Storm Forecasting** | Assess restoration scenarios. Finalize restoration sequencing plans. Coordinate with emergency management. |
| **Immediate Pre-Storm** | Oversee crew and equipment staging. Finalize switching plans. Prepare control room for event operations. |
| **Storm Impact** | Direct grid switching. Manage fault isolations and service restoration. |
| **Restoration** | Manage fault isolation and service restoration. Coordinate with field crews and EOC. Report operational performance. |
| **Post Event** | Verify restoration completeness. Plan system improvements. |

---

### 10. Distribution System Operator (DSO)

*Named persona: Rocky John*

| Phase | Responsibilities |
|---|---|
| **Seasonal Readiness** | Validate OMS/DMS readiness for mass outages. Confirm DER strategies for hurricane-impacted zones. Validate vegetation clearance and feeder hardening. Identify and prioritize hurricane wind exposure constraints. Forecast DER growth and hurricane reliability impacts. |
| **Pre-Storm Forecasting** | Simulate feeder outages for hurricane wind and impact scenarios. Coordinate with Grid Ops for restoration sequencing. Incorporate hurricane contingency plans. Identify feeders needing storm-hardening reinforcement. |
| **Immediate Pre-Storm** | Pre-stage mobile substations and crews outside hurricane impact zones. Validate DER conditions and feeder switching readiness. Accelerate targeted maintenance for critical feeders in hurricane path. Validate resource allocation. |
| **Storm Impact** | Monitor DER performance during hurricane-induced instability. Enter feeder reconfiguration for wind-damaged areas. Manage fault isolation. Assist restoration prioritization. |
| **Restoration** | Update OMS/DMS with hurricane outage data. Coordinate with field crews. Analyze feeder failure patterns from hurricane impact. Verify restoration progress and customer status. |
| **Post Event** | Recommend automation upgrades for hurricane resilience. Update feeder advanced configuration models. Recommend distribution hardening investments. |

---

### 11. Distribution Planner

*Named persona: Rocky John*

| Phase | Responsibilities |
|---|---|
| **Seasonal Readiness** | Develop outage/restoration playbooks. Validate switching sequences for contingencies. Train control room staff on emergency protocols. Assess seasonal equipment ratings and storm-rated equipment needs. |
| **Pre-Storm Forecasting** | Assess restoration scenarios. Finalize restoration sequencing plans. Coordinate with emergency management. Identify feeders requiring storm-hardening reinforcement plans. Evaluate hurricane-rated equipment needs. |
| **Immediate Pre-Storm** | Oversee crew and equipment staging. Finalize switching plans. Prepare control room for event operations. |
| **Storm Impact** | Direct grid switching. Manage fault isolations and service restoration. |
| **Restoration** | Verify restoration completeness. Report operational performance metrics. Coordinate with field crews and EOC. |
| **Post Event** | Plan system improvements. Recommend distribution resilience upgrades. |

---

### 12. Distribution Operations Manager

*Named persona: Rocky John*

| Phase | Responsibilities |
|---|---|
| **Seasonal Readiness** | Develop outage/restoration playbooks. Validate switching sequences for contingencies. Train control room staff on emergency protocols. |
| **Pre-Storm Forecasting** | Assess restoration scenarios. Finalize restoration sequencing plans. Coordinate with emergency management. |
| **Immediate Pre-Storm** | Oversee crew and equipment staging. Finalize switching plans. Prepare control room for event operations. |
| **Storm Impact** | Direct grid switching. Manage fault isolations and service restoration. |
| **Restoration** | Manage fault isolation and service restoration. Coordinate with field crews and EOC. Verify restoration completeness. |
| **Post Event** | Plan system improvements. Report operational performance. |

---

## Key Structural Observations

1. **Temporal progression follows the storm lifecycle**: Unlike the blue-sky operations matrix, this journey maps to a single event arc — from seasonal preparedness through post-event improvement — creating a natural incident command cadence.

2. **Dual-track response structure**: The matrix maintains parallel tracks for transmission (TSO, Transmission Planner, Transmission Ops Manager) and distribution (DSO, Distribution Planner, Distribution Ops Manager), each with a named persona "Rocky John," suggesting scenario-based role-play or exercise design.

3. **Cybersecurity as a first-class concern**: Unlike typical grid operations matrices, this document elevates cybersecurity and OT security as dedicated personas, reflecting the reality that extreme weather events create cyber-attack windows (compromised communications, emergency access, temporary configurations).

4. **Field-to-office coordination intensity**: The matrix highlights the sharp transition from office-based planning (Seasonal Readiness) to field-centric execution (Storm Impact), with the Immediate Pre-Storm phase serving as the critical handoff point where coordination complexity peaks.

5. **Asset management spans the full lifecycle**: Asset Management and Maintenance Engineer roles span all phases, providing continuity from risk profiling through damage assessment to post-event model updates — the natural data pipeline for digital twin applications.

6. **Restoration is not the end**: The explicit "Post Event Continuous Improvement" column (48 hours to 30 days) emphasizes that resilience is built in the recovery phase, not just the preparedness phase — an important design consideration for any agentic system supporting grid operations.

---

*Note: Some cell content was partially reconstructed from OCR of a rasterized image. Minor details may have artifacts. The structural layout, persona definitions, phase descriptions, and key responsibilities are faithfully captured.*
