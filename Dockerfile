FROM busybox
COPY rootfs /
RUN chmod +x /opt/rancher/entrypoint-wrapper.py \
	&& chmod +x /pause
VOLUME ["/opt/rancher"]
CMD ["/pause"]