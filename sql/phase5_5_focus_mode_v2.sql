/*
    LifeOS AI — Phase 5.5 Focus Mode v2.0
    SQL Server migration

    Run this file once after the original phase5_5_focus_mode.sql migration.
*/

IF COL_LENGTH('focus_sessions', 'goal') IS NULL
    ALTER TABLE focus_sessions ADD goal NVARCHAR(MAX) NULL;
GO

IF COL_LENGTH('focus_sessions', 'focus_method') IS NULL
    ALTER TABLE focus_sessions ADD focus_method NVARCHAR(30) NOT NULL CONSTRAINT DF_focus_sessions_focus_method DEFAULT 'pomodoro';
GO

IF COL_LENGTH('focus_sessions', 'break_minutes') IS NULL
    ALTER TABLE focus_sessions ADD break_minutes INT NOT NULL CONSTRAINT DF_focus_sessions_break_minutes DEFAULT 5;
GO

IF COL_LENGTH('focus_sessions', 'planned_cycles') IS NULL
    ALTER TABLE focus_sessions ADD planned_cycles INT NOT NULL CONSTRAINT DF_focus_sessions_planned_cycles DEFAULT 1;
GO

IF COL_LENGTH('focus_sessions', 'completed_cycles') IS NULL
    ALTER TABLE focus_sessions ADD completed_cycles INT NOT NULL CONSTRAINT DF_focus_sessions_completed_cycles DEFAULT 0;
GO

IF COL_LENGTH('focus_sessions', 'current_cycle') IS NULL
    ALTER TABLE focus_sessions ADD current_cycle INT NOT NULL CONSTRAINT DF_focus_sessions_current_cycle DEFAULT 1;
GO

IF COL_LENGTH('focus_sessions', 'current_phase') IS NULL
    ALTER TABLE focus_sessions ADD current_phase NVARCHAR(20) NOT NULL CONSTRAINT DF_focus_sessions_current_phase DEFAULT 'focus';
GO

IF COL_LENGTH('focus_sessions', 'goal_result') IS NULL
    ALTER TABLE focus_sessions ADD goal_result NVARCHAR(20) NULL;
GO

IF COL_LENGTH('focus_sessions', 'focus_rating') IS NULL
    ALTER TABLE focus_sessions ADD focus_rating INT NULL;
GO

IF COL_LENGTH('focus_sessions', 'difficulty_rating') IS NULL
    ALTER TABLE focus_sessions ADD difficulty_rating INT NULL;
GO

IF COL_LENGTH('focus_sessions', 'energy_rating') IS NULL
    ALTER TABLE focus_sessions ADD energy_rating INT NULL;
GO

PRINT 'Phase 5.5 Focus Mode v2.0 migration completed.';
GO
