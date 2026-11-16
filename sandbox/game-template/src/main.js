import Phaser from "phaser";

class MenuScene extends Phaser.Scene {
  constructor() {
    super("Menu");
  }

  create() {
    const { width, height } = this.scale;
    this.add
      .text(width / 2, height / 2 - 60, "示例游戏", { fontSize: "48px", color: "#ffffff" })
      .setOrigin(0.5);
    this.add
      .text(width / 2, height / 2 + 40, "点击开始", { fontSize: "26px", color: "#8be9fd" })
      .setOrigin(0.5)
      .setInteractive({ useHandCursor: true })
      .on("pointerdown", () => this.scene.start("Play"));
  }
}

class PlayScene extends Phaser.Scene {
  constructor() {
    super("Play");
  }

  create() {
    this.cameras.main.setBackgroundColor("#1d3557");
    this.player = this.add.rectangle(120, this.scale.height / 2, 44, 44, 0x8be9fd);
    this.cursors = this.input.keyboard.createCursorKeys();
    this.add.text(16, 16, "方向键 / 触屏移动", { fontSize: "16px", color: "#ffffff" });
    this.add
      .text(16, 44, "重开", { fontSize: "18px", color: "#ffb86c" })
      .setInteractive({ useHandCursor: true })
      .on("pointerdown", () => this.scene.restart());
    this.input.on("pointerdown", (pointer) => {
      this.player.x = pointer.x;
      this.player.y = pointer.y;
    });
  }

  update() {
    const speed = 5;
    if (this.cursors.left.isDown) this.player.x -= speed;
    if (this.cursors.right.isDown) this.player.x += speed;
    if (this.cursors.up.isDown) this.player.y -= speed;
    if (this.cursors.down.isDown) this.player.y += speed;
  }
}

new Phaser.Game({
  type: Phaser.AUTO,
  parent: "game",
  width: 960,
  height: 540,
  backgroundColor: "#0b0c10",
  scale: { mode: Phaser.Scale.FIT, autoCenter: Phaser.Scale.CENTER_BOTH },
  scene: [MenuScene, PlayScene],
});
