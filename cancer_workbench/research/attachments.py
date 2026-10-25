"""Server-validated chat attachments. Only stable IDs and eligible task context enter the LLM."""
from __future__ import annotations
from . import runtime


def context(attachments) -> str:
    if not isinstance(attachments,list) or not 1 <= len(attachments) <= 4:
        raise ValueError("Attach between one and four research inputs.")
    lines=[]
    for item in attachments:
        if not isinstance(item,dict) or set(item)-{"input_id","workflow_id"} or "input_id" not in item:
            raise ValueError("Each attachment needs input_id and optionally workflow_id. Reference labels are not attachment fields.")
        path,meta=runtime.resolve_input(item["input_id"])
        line=f"Attached local input ID: {meta['id']}; format: {meta['format']}."
        workflow=item.get("workflow_id")
        if workflow:
            _,model=runtime.profile(workflow)
            if meta["format"] not in model["formats"]:
                raise ValueError("The selected task does not accept this input format.")
            if model["backend"]=="pixels":
                runtime.pixels(path,model["preprocessing"])
            line+=(f" The user selected task {model['task']}, modality {model['modality']}, anatomy {model['anatomy']}."
                   f" Use installed model_id {model['id']} with run_specialist; inputs must contain only input_id {meta['id']}."
                   " Obtain the actual tool result before explaining a prediction. Do not infer a label from an attachment name.")
        else:
            line+=" Ask which supported research task/modality the user intends if it is not clear; do not infer modality from the extension or pretend to see the pixels."
        lines.append(line)
    return "\n\nServer-validated local research attachments:\n"+"\n".join(lines)
