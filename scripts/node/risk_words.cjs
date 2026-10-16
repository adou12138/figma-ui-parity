/**
 * 风险词表单源（7.x 安全分级共用）。
 *
 * 背景：discover_scenarios.py（场景生成）与 run_journeys.cjs（跨页旅程）曾各自维护一份
 * DANGER_WORDS，且内容不一致——js 版是超集（多「销毁 / signout / sign-out / unbind /
 * destroy」）。词表漂移的后果是同一个按钮在场景生成里被判 safe、在旅程里被判 danger，
 * 直接违反「分级执行边界」：一侧放行点击、一侧拒绝执行。
 *
 * 维护纪律：改词表只改这一处，然后同步 scripts/discover_scenarios.py 的同名常量，
 * 并由 scripts/tests/test_risk_words_parity.py 对拍两边集合，不一致即测试红。
 * CAUTION_WORDS 目前只有 python 侧消费（场景 safety 分级），js 侧只分 danger/非 danger，
 * 仍在此统一定义，避免将来 js 要用时再抄第三份。
 */

const DANGER_WORDS = ['删除', '清空', '退出', '解绑', '退款', '支付', '下线', '注销', '移除', '销毁',
  'delete', 'remove', 'logout', 'signout', 'sign-out', 'unbind', 'destroy'];

const CAUTION_WORDS = ['保存', '提交', '创建', '新增', '导入', '上传', '发送', '同步', '发布', '确认', '绑定',
  'save', 'submit', 'create', 'import', 'upload', 'send', 'sync', 'publish'];

module.exports = { DANGER_WORDS, CAUTION_WORDS };
