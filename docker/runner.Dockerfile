# Execution Environment del runner Ansible (equivalente a ansible-builder, sin la herramienta).
FROM python:3.12-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends openssh-client sshpass \
 && rm -rf /var/lib/apt/lists/* \
 && useradd -m runner

COPY ansible/requirements.yml /tmp/requirements.yml
RUN pip install --no-cache-dir "ansible-core==2.17.*" ansible-runner "paramiko<4" \
        netaddr boto3 botocore jmespath awscli \
 && ansible-galaxy collection install -r /tmp/requirements.yml -p /usr/share/ansible/collections

COPY ansible/ /runner/project/
WORKDIR /runner/project
USER runner

# El worker lanza la tarea con: PLAYBOOK, PORTAL_SITE_CODE, PORTAL_JOB_ID, PORTAL_API_URL,
# PORTAL_RUNNER_TOKEN, y opcionalmente ANSIBLE_TAGS.
ENTRYPOINT ["sh", "-c", "ansible-playbook playbooks/${PLAYBOOK} ${ANSIBLE_TAGS:+--tags $ANSIBLE_TAGS} -e artifacts_dir=/tmp/artifacts && aws s3 cp --recursive /tmp/artifacts s3://${ARTIFACTS_BUCKET}/jobs/${PORTAL_JOB_ID}/ || true"]
