"use client";

export type PrivacyValue = boolean | null;

type PrivacySelectorProps = {
  value: PrivacyValue;
  onChange: (value: boolean) => void;
};

/** 上传页 / 实时页「开始生成会议纪要」按钮上方的隐私选择（是/否，初始都不选）。 */
export function PrivacySelector({ value, onChange }: PrivacySelectorProps) {
  return (
    <div className="privacy-selector">
      <span className="privacy-selector-label">{"是否涉及隐私内容"}</span>
      <div className="privacy-selector-options">
        <button
          type="button"
          className={value === true ? "privacy-chip privacy-chip-active" : "privacy-chip"}
          onClick={() => onChange(true)}
        >
          {"是"}
        </button>
        <button
          type="button"
          className={value === false ? "privacy-chip privacy-chip-active" : "privacy-chip"}
          onClick={() => onChange(false)}
        >
          {"否"}
        </button>
      </div>
    </div>
  );
}

type PrivacyModalProps = {
  open: boolean;
  onChoose: (value: boolean) => void;
  onCancel: () => void;
};

/** 未选择隐私就点生成时弹出的小窗，选择是/否后才继续生成。 */
export function PrivacyModal({ open, onChoose, onCancel }: PrivacyModalProps) {
  if (!open) return null;
  return (
    <div className="privacy-modal-overlay" role="dialog" aria-modal="true" onClick={onCancel}>
      <div className="privacy-modal-card" onClick={(event) => event.stopPropagation()}>
        <div className="privacy-modal-title">{"是否涉及隐私内容"}</div>
        <div className="privacy-modal-desc">
          {"选择「是」后，之后从历史记录查看该会议需重新输入密码。"}
        </div>
        <div className="privacy-modal-actions">
          <button type="button" className="secondary-button" onClick={() => onChoose(false)}>
            {"否"}
          </button>
          <button type="button" className="primary-button" onClick={() => onChoose(true)}>
            {"是"}
          </button>
        </div>
      </div>
    </div>
  );
}
