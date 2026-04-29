def run_tool(model_output, tools):
    tool_name = model_output["tool"]
    args = model_output["args"]
    return tools[tool_name](**args)
