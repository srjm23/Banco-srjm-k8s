{{- define "image.reference" -}}
{{- if .Values.image.digest -}}
{{- printf "%s@%s" .Values.image.repository .Values.image.digest -}}
{{- else -}}
{{- printf "%s:%s" .Values.image.repository .Values.image.tag -}}
{{- end -}}
{{- end -}}
{{- define "frontend.backendHost" -}}
{{- printf "%s.%s.svc.%s" .Values.backend.serviceName (.Values.backend.namespace | default .Release.Namespace) .Values.clusterDomain -}}
{{- end -}}
