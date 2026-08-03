# Axiom Tech - Incident Management & Resilience Manual

## 1. Incident Severity Definitions
- **SEV-1 (Critical Outage)**: Primary production platform or customer-facing API down. Data breach or total service failure. Maximum response SLA: **15 minutes**. Resolution SLA: **4 hours**.
- **SEV-2 (Major Impact)**: Core functionality degraded, non-critical database latency spiking (> 2s), high error rates (> 5%). Maximum response SLA: **30 minutes**.
- **SEV-3 (Minor Defect)**: Non-blocking bug, internal tool issue, minor UI glitch. Response SLA: **4 hours**.

## 2. Escalation & Communication Flow
1. **Detection**: Alert triggered in PagerDuty / Datadog or manually flagged in Slack `#incident-war-room`.
2. **Incident Commander (IC)**: Assigned immediately to coordinate response.
3. **War Room**: Zoom / Google Meet room created; link posted to `#incident-war-room`.
4. **Status Updates**: Every 30 minutes for SEV-1; every 1 hour for SEV-2.

## 3. Post-Mortem Requirement
- Blameless Post-Mortem document must be authored within **48 hours** of resolution for all SEV-1 and SEV-2 incidents.
