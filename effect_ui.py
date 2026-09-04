"""
エフェクト設定パネル（ブロックエフェクトタブ／アイテムテクスチャ編集タブ共通）。

以前は両タブがほぼ同じフォームを別々に組み立てており、片方だけに機能が
追加されて差が生まれていた（斜めグラデーションの帯の本数・透過度がアイテム側に
無い、枠線系エフェクトがアイテム側に無い、など）。このパネルに一本化することで、
エフェクトの追加やパラメータの変更が自動的に両タブへ反映される。

エフェクトの定義そのもの（内部キー・表示名・フレーム生成）は effect_catalog.py 側。
このモジュールはその表示と入力だけを担当する。

Copyright (c) 2026 旬茶
Licensed under the MIT License.
"""

from PyQt6.QtWidgets import (
    QGroupBox, QFormLayout, QComboBox, QSpinBox, QDoubleSpinBox,
    QPushButton, QColorDialog
)
from PyQt6.QtGui import QColor
from PyQt6.QtCore import pyqtSignal

import effect_catalog as EC


class EffectSettingsPanel(QGroupBox):
    """エフェクト種類＋各パラメータの入力欄をまとめたグループボックス。

    使う側は changed シグナルを購読し、to_settings() で現在の設定辞書を受け取る。
    値を流し込むときは load_from() を使う（内部でシグナルを止めるので、
    呼び出し側で _loading フラグを持つ必要はない）。
    """

    changed = pyqtSignal()

    def __init__(self, title, effect_keys, default_settings, parent=None):
        super().__init__(title, parent)
        self._effect_keys = list(effect_keys)
        self._defaults = dict(default_settings)
        self._loading = False
        self._border_color = self._defaults["border_color"]

        form = QFormLayout(self)

        self.effect_combo = QComboBox()
        for key in self._effect_keys:
            # 表示名は自由に変えてよいが、保存されるのは userData の内部キーの方。
            self.effect_combo.addItem(EC.display_name(key), key)
        self.effect_combo.currentIndexChanged.connect(self._emit_changed)
        form.addRow("エフェクト種類", self.effect_combo)

        self.frame_count_spin = QSpinBox()
        self.frame_count_spin.setRange(2, 64)
        self.frame_count_spin.setValue(self._defaults["frame_count"])
        self.frame_count_spin.valueChanged.connect(self._emit_changed)
        form.addRow("フレーム数（レインボー）", self.frame_count_spin)

        self.frametime_spin = QSpinBox()
        self.frametime_spin.setRange(1, 40)
        self.frametime_spin.setValue(self._defaults["frametime"])
        self.frametime_spin.valueChanged.connect(self._emit_changed)
        form.addRow("1コマの表示時間 (tick)", self.frametime_spin)

        self.thickness_spin = QSpinBox()
        self.thickness_spin.setRange(1, 3)
        self.thickness_spin.setValue(self._defaults["thickness"])
        self.thickness_spin.valueChanged.connect(self._emit_changed)
        form.addRow("枠線の太さ (px)", self.thickness_spin)

        self.border_saturation_spin = QDoubleSpinBox()
        self.border_saturation_spin.setRange(0.0, 1.0)
        self.border_saturation_spin.setSingleStep(0.1)
        self.border_saturation_spin.setValue(self._defaults["border_saturation"])
        self.border_saturation_spin.valueChanged.connect(self._emit_changed)
        form.addRow("枠線の彩度", self.border_saturation_spin)

        self.border_brightness_spin = QDoubleSpinBox()
        self.border_brightness_spin.setRange(0.0, 1.0)
        self.border_brightness_spin.setSingleStep(0.1)
        self.border_brightness_spin.setValue(self._defaults["border_brightness"])
        self.border_brightness_spin.valueChanged.connect(self._emit_changed)
        form.addRow("枠線の明るさ", self.border_brightness_spin)

        # 「枠線」（固定色）で使う色。「レインボー＋枠線」「枠線（レインボー）」は
        # 上の彩度・明るさから毎フレーム自動で色を決めるので、こちらは使わない。
        self.border_color_btn = QPushButton()
        self.border_color_btn.clicked.connect(self.on_choose_border_color)
        self._update_border_color_button()
        form.addRow("枠線の色（固定色）", self.border_color_btn)

        self.gradient_band_count_spin = QSpinBox()
        self.gradient_band_count_spin.setRange(1, 12)
        self.gradient_band_count_spin.setValue(self._defaults["gradient_band_count"])
        self.gradient_band_count_spin.setToolTip(
            "絵の対角線の中に、虹色の帯を何本並べるか。多いほど帯が細かくなります。"
        )
        self.gradient_band_count_spin.valueChanged.connect(self._emit_changed)
        form.addRow("帯の本数（斜めグラデ）", self.gradient_band_count_spin)

        self.gradient_transparency_spin = QDoubleSpinBox()
        self.gradient_transparency_spin.setRange(0.0, 1.0)
        self.gradient_transparency_spin.setSingleStep(0.1)
        self.gradient_transparency_spin.setValue(self._defaults["gradient_transparency"])
        self.gradient_transparency_spin.setToolTip(
            "値を上げるほど、元の絵の模様（陰影）が透けて見えるようになります"
            "（虹色の主張はその分弱まります）。0なら虹色で完全に上書きします。"
        )
        self.gradient_transparency_spin.valueChanged.connect(self._emit_changed)
        form.addRow("透過度（斜めグラデ）", self.gradient_transparency_spin)

        self.dark_factor_spin = QDoubleSpinBox()
        self.dark_factor_spin.setRange(0.0, 1.0)
        self.dark_factor_spin.setSingleStep(0.05)
        self.dark_factor_spin.setValue(self._defaults["dark_factor"])
        self.dark_factor_spin.valueChanged.connect(self._emit_changed)
        form.addRow("点滅時の暗さ", self.dark_factor_spin)

        self._all_widgets = (
            self.effect_combo, self.frame_count_spin, self.frametime_spin,
            self.thickness_spin, self.border_saturation_spin,
            self.border_brightness_spin, self.border_color_btn,
            self.gradient_band_count_spin, self.gradient_transparency_spin,
            self.dark_factor_spin,
        )
        self.set_editing_enabled(False)

    # ------------------------------------------------------------------
    def _emit_changed(self, *_args):
        if self._loading:
            return
        self.update_param_visibility()
        self.changed.emit()

    def current_effect_key(self):
        return self.effect_combo.currentData()

    def set_effect_key(self, key):
        index = self.effect_combo.findData(key)
        if index >= 0:
            self.effect_combo.setCurrentIndex(index)

    def set_editing_enabled(self, enabled: bool):
        for w in self._all_widgets:
            w.setEnabled(enabled)
        self.update_param_visibility()

    def update_param_visibility(self):
        """今選ばれているエフェクトが使わないパラメータは触れないようにする。
        （どのエフェクトが何を使うかは effect_catalog 側の集合で判定する）"""
        key = self.current_effect_key()
        editing = self.effect_combo.isEnabled()
        self.frame_count_spin.setEnabled(editing and key in EC.USES_FRAME_COUNT)
        self.frametime_spin.setEnabled(editing and key != EC.NONE)
        self.thickness_spin.setEnabled(editing and key in EC.USES_THICKNESS)
        self.border_saturation_spin.setEnabled(editing and key in EC.USES_BORDER_HSV)
        self.border_brightness_spin.setEnabled(editing and key in EC.USES_BORDER_HSV)
        self.border_color_btn.setEnabled(editing and key in EC.USES_BORDER_COLOR)
        gradient = editing and key in EC.USES_GRADIENT
        self.gradient_band_count_spin.setEnabled(gradient)
        self.gradient_transparency_spin.setEnabled(gradient)
        self.dark_factor_spin.setEnabled(editing and key in EC.USES_DARK_FACTOR)

    # ------------------------------------------------------------------
    def load_from(self, settings):
        """保存済みの設定辞書をフォームに反映する。反映中は changed を出さない。
        キーが欠けている旧データでも落ちないよう、すべて既定値で補う。"""
        self._loading = True
        try:
            def g(name):
                return settings.get(name, self._defaults[name])

            key = EC.normalize_effect(settings.get("effect"), default=self._defaults["effect"])
            self.set_effect_key(key)
            self.frame_count_spin.setValue(g("frame_count"))
            self.frametime_spin.setValue(g("frametime"))
            self.thickness_spin.setValue(g("thickness"))
            self.border_saturation_spin.setValue(g("border_saturation"))
            self.border_brightness_spin.setValue(g("border_brightness"))
            self.dark_factor_spin.setValue(g("dark_factor"))
            self._border_color = g("border_color")
            self._update_border_color_button()
            self.gradient_band_count_spin.setValue(g("gradient_band_count"))
            self.gradient_transparency_spin.setValue(g("gradient_transparency"))
        finally:
            self._loading = False
        self.update_param_visibility()

    def to_settings(self):
        """フォームの現在値を設定辞書にして返す。effect は内部キー。"""
        return {
            "effect": self.current_effect_key(),
            "frame_count": self.frame_count_spin.value(),
            "frametime": self.frametime_spin.value(),
            "thickness": self.thickness_spin.value(),
            "border_saturation": self.border_saturation_spin.value(),
            "border_brightness": self.border_brightness_spin.value(),
            "border_color": self._border_color,
            "gradient_band_count": self.gradient_band_count_spin.value(),
            "gradient_transparency": self.gradient_transparency_spin.value(),
            "dark_factor": self.dark_factor_spin.value(),
        }

    # ------------------------------------------------------------------
    @property
    def border_color(self):
        return self._border_color

    @border_color.setter
    def border_color(self, value):
        self._border_color = value
        self._update_border_color_button()

    def _update_border_color_button(self):
        color = self._border_color
        r, g, b, _a = EC.hex_to_rgba(color)
        # 明るい色の上に白文字だと読みにくいので、明度に応じて文字色を切り替える
        luminance = (0.299 * r + 0.587 * g + 0.114 * b)
        text_color = "#000000" if luminance > 140 else "#ffffff"
        self.border_color_btn.setText(color)
        self.border_color_btn.setStyleSheet(
            f"background-color: {color}; color: {text_color}; border: 1px solid #555;"
        )

    def on_choose_border_color(self):
        chosen = QColorDialog.getColor(QColor(self._border_color), self, "枠線の色を選択")
        if not chosen.isValid():
            return
        self._border_color = EC.rgb_to_hex(chosen.red(), chosen.green(), chosen.blue())
        self._update_border_color_button()
        self._emit_changed()
