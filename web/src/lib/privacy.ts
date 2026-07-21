// 「生成后首次查看免密」一次性标记：生成成功跳转详情页前写入，
// 详情页隐私门首次读取后立即清除，之后再从历史进入即需密码。

const FRESH_PREFIX = "meeting-fresh:";

export function markMeetingFresh(meetingId: number | string): void {
  if (typeof window === "undefined") return;
  try {
    window.sessionStorage.setItem(`${FRESH_PREFIX}${meetingId}`, "1");
  } catch {
    // sessionStorage 不可用时忽略：退化为需要输入密码
  }
}

export function consumeMeetingFresh(meetingId: number | string): boolean {
  if (typeof window === "undefined") return false;
  try {
    const key = `${FRESH_PREFIX}${meetingId}`;
    const fresh = window.sessionStorage.getItem(key) === "1";
    if (fresh) {
      window.sessionStorage.removeItem(key);
    }
    return fresh;
  } catch {
    return false;
  }
}
