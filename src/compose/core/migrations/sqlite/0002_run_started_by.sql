-- Who started the run (the git user name, else the OS user); NULL for runs before this.
ALTER TABLE runs ADD COLUMN started_by TEXT;
