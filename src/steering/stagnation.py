class StagnationMonitor:
    """
    Detects if an agent is stuck in a loop (e.g., repeatedly apologizing,
    not editing files, or failing with the exact same error).
    """
    def __init__(self, max_consecutive_failures: int = 3):
        self.max_failures = max_consecutive_failures
        self.turns_without_edits = 0
        self.last_error_hash = None
        self.same_error_count = 0

    def record_turn(self, files_edited: int, current_error: str = None) -> bool:
        """
        Updates metrics based on the agent's turn.
        Returns True if the agent is considered stagnant.
        """
        # 1. Did the agent edit any files?
        if files_edited == 0:
            self.turns_without_edits += 1
        else:
            self.turns_without_edits = 0

        # 2. Is the agent hitting the exact same error repeatedly?
        if current_error:
            # A simple hash to compare errors roughly. In production, 
            # maybe strip line numbers to catch semantic duplicates.
            error_hash = hash(current_error)
            if self.last_error_hash == error_hash:
                self.same_error_count += 1
            else:
                self.same_error_count = 1
                self.last_error_hash = error_hash
        else:
            self.same_error_count = 0
            self.last_error_hash = None

        # Check thresholds
        is_stuck_on_edits = self.turns_without_edits >= self.max_failures
        is_stuck_on_errors = self.same_error_count >= self.max_failures

        return is_stuck_on_edits or is_stuck_on_errors

    def reset(self):
        """Clears metrics after an intervention."""
        self.turns_without_edits = 0
        self.same_error_count = 0
        self.last_error_hash = None

    def get_intervention_prompt(self) -> str:
        """Returns a stern prompt to inject when the agent is stuck."""
        if self.turns_without_edits >= self.max_failures:
            return (
                "**SYSTEM INTERVENTION:** You have spent multiple turns talking "
                "or apologizing without making any material changes to the files. "
                "Stop planning or explaining. Use the edit/write tools immediately "
                "to modify the code and advance the task."
            )
        if self.same_error_count >= self.max_failures:
            return (
                "**SYSTEM INTERVENTION:** You are stuck in an error loop. The exact "
                "same test/compilation error has occurred multiple times in a row. "
                "Your current approach is not working. Discard it. Look at the context, "
                "re-evaluate the root cause, and try a completely different solution."
            )
        return ""
