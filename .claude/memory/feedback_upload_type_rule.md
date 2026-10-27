---
name: feedback-upload-type-rule
description: 上传数据CSV中「上传类型」的判断规则
metadata:
  type: feedback
---

上传类型的判断依据是上传人账号，不是素材命名或日期：
- 上传人是 `hancg` → 上传类型 = `拒审二传`
- 上传人是编导本人账号（weijiali / duhaozheng / quminbj / jiazijinbj / wutingyubj / wangyadibj01 等）→ 上传类型 = `新素材`

**Why:** 用户明确纠正过两次，命名日期不能作为判断依据，账号才是唯一标准。

**How to apply:** 每次生成上传数据_增强版_MMDD.csv 时，填写「上传类型」列前先看「上传人」列，遇到 hancg 就填拒审二传，其余填新素材。
