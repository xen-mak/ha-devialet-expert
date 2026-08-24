# Devialet Expert (non-Pro) for Home Assistant

[![Validate HACS integration](https://github.com/xen-mak/devialet-expert-hacs/actions/workflows/validate.yml/badge.svg)](https://github.com/xen-mak/devialet-expert-hacs/actions/workflows/validate.yml)

這是 **Devialet Expert（非 Pro、Core Infinity 之前）**擴大機的本機 Home Assistant `media_player` 自訂整合。它移植自 [DeviMote](https://github.com/gnulabis/devimote) 的逆向 UDP 協定實作，完全在區域網路內運作，不使用雲端帳號、密碼或第三方服務。[1]

> **相容性範圍：**本專案僅支援 Devimote 已明確支援的 **Devialet Expert non-Pro** 硬體。本整合不應安裝在 Pro 機種或已配備 Core Infinity 板的機種上；這些裝置的控制協定未經本專案驗證。[1]

## 功能

此整合將每一台擴大機建立為一個 Home Assistant `media_player` 實體。所有實體狀態會由最近的 UDP 狀態廣播快取提供；Home Assistant 的 entity 屬性本身不進行網路 I/O，符合官方 media player 實作模式。[2]

| 需求 | Home Assistant 行為 | 實作細節 |
| --- | --- | --- |
| 音量與上下限 | `media_player.volume_set` 與音量滑桿 | 以 dB 設定 min/max，滑桿依該範圍正規化為 0–100%；硬體半 dB 解析度 |
| 靜音／取消靜音 | `media_player.volume_mute` | 傳送明確目標狀態，而非依賴可能過時的 toggle 狀態 |
| 來源清單與切換 | `media_player.select_source` | 顯示擴大機廣播的啟用輸入名稱；選取時映射回 UDP 通道 index |
| 電源開／關 | `media_player.turn_on`、`media_player.turn_off` | 對應開機與 standby 的明確命令 |
| 其他 DeviMote 狀態 | 額外 state attributes 與 diagnostics | 裝置名稱、IP、通道 index、完整來源對照表、dB／raw 音量、CRC 與連線狀態 |
| 新增擴大機 | 圖形化 Config Flow | 可掃描區域網路中的 UDP 狀態廣播，也可手動輸入 IP／hostname |

## 安裝

本儲存庫採用 HACS 規定的單一整合目錄結構，包含根目錄 `hacs.json` 與 `custom_components/devialet_expert/`；它可作為 **HACS custom repository** 安裝。[3] [4]

| 步驟 | 操作 |
| --- | --- |
| 1 | 在 GitHub 將本專案發佈為**公開**儲存庫 `xen-mak/devialet-expert-hacs`。HACS 只支援公開 GitHub 儲存庫。[4] |
| 2 | 在 Home Assistant 開啟 **HACS → Integrations → 右上角三點 → Custom repositories**。 |
| 3 | 貼上 `https://github.com/xen-mak/devialet-expert-hacs`，類型選擇 **Integration**，再按 **Add**。[5] |
| 4 | 在 HACS 搜尋並下載 **Devialet Expert (non-Pro)**，然後重新啟動 Home Assistant。 |
| 5 | 前往 **Settings → Devices & services → Add integration**，搜尋 **Devialet Expert (non-Pro)**。 |

若不使用 HACS，可將 `custom_components/devialet_expert` 複製至 Home Assistant 的 `<config>/custom_components/devialet_expert`，再重新啟動 Home Assistant。

## 新增擴大機

設定流程有兩種方式。Home Assistant 的 config flow 是官方建議的 UI 設定機制；探索結果會要求使用者確認後才建立設定項。[6]

| 方式 | 適用情境 | 操作 |
| --- | --- | --- |
| **掃描區域網路** | Home Assistant 與擴大機在同一個可接收 UDP broadcast 的網段 | 選擇「掃描區域網路」，等待約五秒，再從發現清單選擇名稱與 IP。 |
| **手動輸入位址** | 掃描未發現裝置、使用固定 DHCP 位址，或網路架構阻擋 broadcast | 選擇「手動輸入位址」，輸入擴大機 IP 或可解析的 hostname。整合會等待該位址送出有效 CRC 的狀態封包。 |

擴大機會在 UDP **45454** 廣播 512-byte 狀態封包，並在 UDP **45455** 接收控制封包；這是 Devimote 已記錄的本機逆向協定。[1] Home Assistant 主機必須能接收 45454 的 UDP broadcast，並能對擴大機送出 UDP 45455 封包。若使用容器化 Home Assistant，請確認容器網路模式與防火牆沒有阻擋這兩種流量。

本協定沒有已驗證的固定序號或 MAC 可作為硬體識別碼，因此本整合不會把可變的 IP 位址冒充成裝置序號。若 DHCP 租約變更，請在該整合的 **Reconfigure** 選項輸入新 IP 或 hostname。

## 音量限制與 dB 對應

在整合的 **Configure** 選項中，可設定「最小音量（dB）」與「最大音量（dB）」。預設值是 **−97.5 dB** 至 **−10.0 dB**，也就是此協定可確認的完整實體範圍。選擇較保守的最大值可避免儀表板、語音助理或自動化把擴大機設得過大聲。

擴大機狀態封包中的原始音量 byte 會依下式轉換：

```text
volume_db = (raw_volume - 195) / 2
```

`media_player.volume_level` 則是在使用者選擇的 dB 邊界內轉為 0.0–1.0；Home Assistant 官方規格要求此屬性採用該範圍。[2] 擴大機或原廠遙控器在整合外調整音量時，`volume_db` 與 `raw_volume` 額外屬性仍保留真實值；超出使用者 UI 邊界的值會在滑桿端夾至 0% 或 100%。

## 狀態、可用性與除錯

整合每兩秒等待一個最新的狀態廣播。若未收到設定主機送出的有效 CRC 封包，實體會顯示為 **unavailable**，以免將過期資料誤當成目前狀態。有效資料會公開於 state attributes，方便建立進階自動化。

| Attribute | 說明 |
| --- | --- |
| `device_name`、`ip_address` | 廣播內的裝置名稱與目前回報 IP |
| `channel_index`、`sources_by_channel` | 目前輸入及 protocol channel 對來源名稱的完整對照 |
| `volume_db`、`raw_volume` | 實際 dB 音量及原始封包 byte |
| `crc_ok`、`connected` | 最後一個封包的完整性與連線結果 |
| `configured_host` | 設定中輸入的 IP／hostname |
| `volume_min_db`、`volume_max_db` | 套用於 Home Assistant 音量滑桿與寫入命令的範圍 |

可從 **Settings → Devices & services → Devialet Expert (non-Pro) → Download diagnostics** 匯出已遮罩主機資訊的診斷快照，用於回報問題。

## 開發、驗證與授權

本專案包含不需實體擴大機的協定測試，覆蓋 CRC-16/CCITT-FALSE、狀態封包解碼、明確電源控制，以及第 8–14 來源通道的特殊編碼。請執行：

```bash
python3 -m unittest discover -s tests -v
```

`.github/workflows/validate.yml` 會使用 HACS 官方驗證 action 檢查儲存庫結構。[7] 協定實作衍生自 GPL-3.0-or-later 的 Devimote，因此本專案亦採用 **GPL-3.0-or-later**；詳見 [LICENSE](LICENSE)。

## References

[1] [gnulabis/devimote — DeviMote GitHub repository](https://github.com/gnulabis/devimote)

[2] [Home Assistant Developer Docs — Media player entity](https://developers.home-assistant.io/docs/core/entity/media-player/)

[3] [HACS — Publishing integrations](https://www.hacs.xyz/docs/publish/integration/)

[4] [HACS — General publishing requirements](https://www.hacs.xyz/docs/publish/start/)

[5] [HACS — Custom repositories](https://www.hacs.xyz/docs/faq/custom_repositories/)

[6] [Home Assistant Developer Docs — Config flow](https://developers.home-assistant.io/docs/core/integration/config_flow/)

[7] [HACS — GitHub Action validation](https://www.hacs.xyz/docs/publish/action/)
