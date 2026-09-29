class MockProviderError(Exception):
    pass


class DeterministicMockProvider:
    """Produce an explicit demo response without making a network request."""

    def generate(self, *, option, prompt, context, attachments):
        if "[[mock-error]]" in prompt:
            raise MockProviderError("The mock provider was asked to simulate a failure.")

        files = ", ".join(attachment["name"] for attachment in attachments) or "none"
        context_note = "Your saved instructions and recent messages were included." if context else "No saved context was added."
        return (
            f"Mock response for the {option['provider_label']} target ({option['tier']} demo model).\n\n"
            f"Prompt received: {prompt.strip()}\n\n"
            f"Attachments received: {files}. {context_note}\n\n"
            "This deterministic response confirms that LightChat routed the request through its mock provider. "
            "It is not a response from the real provider."
        )


def get_provider(mode):
    if mode == "mock":
        return DeterministicMockProvider()
    return None
