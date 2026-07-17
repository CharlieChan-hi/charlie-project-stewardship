# Legacy Update-Plan Pointer

Existing file detected: `[[existing_path]]`

This compatibility template does not define a second update-plan format. Current
workflows use separate, workflow-specific files below `architecture_reports/latest/`
and print the exact destination they selected. Use that printed path rather than
assuming one global adoption-plan filename. Each plan records the exact path,
observed difference, proposed action, and authorization boundary while leaving the
existing file untouched.
