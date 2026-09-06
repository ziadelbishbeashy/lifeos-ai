I20 — Adaptive Experience Profiles

Active experiences:
- Student
- Self-Learning
- Professional
- Personal

Principles:
- One LifeOS core; no separate apps.
- Profiles change defaults, labels, Home emphasis and Ask LifeOS suggestions.
- Modules are emphasized only when Student/Self-Learning is enabled.
- Existing users choose once through onboarding; registration collects the choice up front.
- Settings allows changing the primary experience and enabling additional experiences.
- User-selected experience is available as trusted preference context to project Ask LifeOS reasoning.
- Team/shared-workspace roles and Admin remain separate future concepts.

Migration compatibility:
- 20260831_0002 is retained as a no-op compatibility revision for the retired Goals prototype.
- 20260901_0001 adds user_experience_profiles.
- If an earlier local Goals build already created prototype goal tables, this patch does not delete them automatically. They are unused and should only be removed later after a backup.
