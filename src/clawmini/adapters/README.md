# `adapters` 外部适配层

本目录用于封装“智能体与真实系统交互”的边界。

## 当前模块

- `qq_adapter.py`：
	- `QQMessage`：消息结构
	- `QQGateway`：网关协议
	- `MockQQGateway`：本地模拟实现
	- `WindowsQQGateway`：Windows UI 自动化骨架（需后续补齐真实步骤）

## 为什么要有这一层

- 业务逻辑不直接耦合具体客户端。
- 未来替换为 Windows Automation / QQ Bot 框架时，只需替换适配层。
- 测试时可以使用 Mock 适配器，避免真实副作用。

## 扩展示例

当前已支持在工具层通过 `set_gateway` 切换网关：
1. `mode=mock`：默认离线模式
2. `mode=windows`：尝试启用 Windows 自动化网关
3. 若依赖或初始化失败，会自动回退到 `mock`
