FROM eclipse-temurin:25-jdk-noble AS tabula-builder

ARG TABULA_JAR=target/tabula.jar

COPY ${TABULA_JAR} /tabula.jar

# Analyze dependencies and create a compact runtime with only required modules.
RUN jdeps --print-module-deps --ignore-missing-deps /tabula.jar > /modules.txt && \
    jlink \
      --add-modules "$(cat /modules.txt)" \
      --strip-debug \
      --no-man-pages \
      --no-header-files \
      --compress=2 \
      --output /jre

# Wrapper script so the container can be used like `tabula-java`.
RUN printf '%s\n' '#!/bin/sh' 'exec /jre/bin/java -jar /tabula.jar "$@"' > /tabula-java && \
    chmod +x /tabula-java

FROM ubuntu:24.04

COPY --from=tabula-builder /jre /jre
COPY --from=tabula-builder /tabula.jar /tabula.jar
COPY --from=tabula-builder /tabula-java /usr/local/bin/tabula-java

ENTRYPOINT ["/usr/local/bin/tabula-java"]
