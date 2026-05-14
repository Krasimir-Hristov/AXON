-- Convert pending_audio from TEXT to JSONB so JSON operators (->, ->>) can be used
-- and the empty-state is idiomatic NULL rather than an empty string.
-- Rows that still hold '' (the previous DEFAULT) are converted to NULL.

-- Step 1: lift the NOT NULL constraint so empty strings can convert to NULL.
ALTER TABLE conversations ALTER COLUMN pending_audio DROP NOT NULL;

-- Step 2: convert type and set idiomatic default.
ALTER TABLE conversations
    ALTER COLUMN pending_audio DROP DEFAULT,
    ALTER COLUMN pending_audio TYPE JSONB
        USING CASE
            WHEN pending_audio = '' OR pending_audio IS NULL THEN NULL
            ELSE pending_audio::jsonb
        END,
    ALTER COLUMN pending_audio SET DEFAULT NULL;
