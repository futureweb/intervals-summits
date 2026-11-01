# The tool's own image, as a Home Assistant app: run as root (Home Assistant owns /data),
# settings from the app's form (/data/options.json), the summit log through ingress.
FROM ghcr.io/futureweb/intervals-summits:0.2.1
USER root
COPY run.sh /run.sh
RUN chmod 755 /run.sh
ENTRYPOINT ["/run.sh"]
CMD []
