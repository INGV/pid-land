from hues.wf_handle import WFHandleHue
from hues.wf_provenance import WFProvenanceHue
# gli altri arriveranno dopo


class Prism:

    def __init__(self, config, log, meta, prov):

        self.config = config
        self.log = log

        #
        # Concrete representations
        #
        self.wf_handle = WFHandleHue(meta)
        self.wf_provenance = WFProvenanceHue(prov)

        #
        # Domain defaults
        #
        self.defaults = {

            "metadata": self.wf_handle,
            "provenance": self.wf_provenance,

            # arriveranno dopo
            # "waveform": self.mseed
            # "catalog": self.rocrate
        }

    async def execute(self, handler, pid, handle, request_type):

        #
        # Version
        #
        if request_type.startswith("version="):
            version = request_type.split("/")[0].split("=")[1]
            await handler._send_version(handle, version)
            return

        #
        # Default domain representations
        #
        if request_type in self.defaults:

            hue = self.defaults[request_type]

            await hue.represent(handler, handle)

            return

        #
        # Human documentation
        #
        if request_type == "document":
            await handler._send_document()
            return

        #
        # Special PID
        #
        if pid == "wf-search":
            await handler._send_wf_search(request_type)
            return

        if pid == "wf-select":
            await handler._send_wf_select(request_type)
            return

        #
        # Latest waveform
        #
        if request_type == "latest":
            await handler._send_latest(handle)
            return

        handler.set_status(404)
        handler.write({"error": "Malformed request"})