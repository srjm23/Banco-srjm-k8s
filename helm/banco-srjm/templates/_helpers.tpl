{{- define "banco-srjm.checksum.runtime" -}}
{{- printf "%s%s" (include (print .Template.BasePath "/frontend-nginx.yaml") .) (include (print .Template.BasePath "/backend-application-secret.yaml") .) | sha256sum -}}
{{- end -}}

{{- define "banco-srjm.checksum.config" -}}
{{- printf "%s%s" (include (print .Template.BasePath "/postgres-config.yaml") .) (include (print .Template.BasePath "/backend-config.yaml") .) | sha256sum -}}
{{- end -}}

{{- define "banco-srjm.checksum.secrets" -}}
{{- printf "%s%s" (include (print .Template.BasePath "/postgres-secret.yaml") .) (include (print .Template.BasePath "/backend-secret.yaml") .) | sha256sum -}}
{{- end -}}
