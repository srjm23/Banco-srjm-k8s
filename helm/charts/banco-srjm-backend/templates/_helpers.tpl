{{- define "image.reference" -}}
{{- if .Values.image.digest -}}
{{- printf "%s@%s" .Values.image.repository .Values.image.digest -}}
{{- else -}}
{{- printf "%s:%s" .Values.image.repository .Values.image.tag -}}
{{- end -}}
{{- end -}}
{{- define "mailpit-image.reference" -}}
{{- if .Values.mailpit.image.digest -}}
{{- printf "%s@%s" .Values.mailpit.image.repository .Values.mailpit.image.digest -}}
{{- else -}}
{{- printf "%s:%s" .Values.mailpit.image.repository .Values.mailpit.image.tag -}}
{{- end -}}
{{- end -}}
