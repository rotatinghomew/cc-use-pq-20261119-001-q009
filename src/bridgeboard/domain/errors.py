"""供 API、导入和领域服务共同使用的业务错误。"""


class BridgeboardError(Exception):
    """可安全映射为业务响应的基础错误。"""


class NotFound(BridgeboardError):
    """请求引用了不存在的项目或事件。"""


class Conflict(BridgeboardError):
    """新事实与已登记身份或当前状态冲突。"""


class InvalidInput(BridgeboardError):
    """输入不能表达有效的业务事实。"""


class BatchRejected(BridgeboardError):
    """整批导入未通过预检，任何记录均未写入。"""

    def __init__(self, issues: list[dict[str, str]]) -> None:
        self.issues = issues
        super().__init__("导入批次未通过校验")
