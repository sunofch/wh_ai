"""个性化联邦 LoRA 微调框架（骨架）。

pj4 子课题 4.1：设备/运营/安全多部门异构数据协同微调仓储决策大模型。
隐私设计：原始数据不出部门，客户端只上传 LoRA 增量参数；
个性化设计：FedAvg 全局聚合后按 α 系数与本地 adapter 混合
（FlexLoRA 式），推理侧由 AdapterRouter 按部门路由专属 adapter。

骨架以小模型验证机制正确性；接入真实 vLLM/Qwen 基座时，把
LoRALinear 替换为 peft 库的注入实现即可，协调与聚合逻辑不变。
"""
