import asyncio, csv, re, sys, time, threading, tkinter as tk
from tkinter import filedialog, scrolledtext
from pathlib import Path
from PIL import Image, ImageOps, ImageEnhance

try:
    import winocr
except ImportError:
    pass

TILT_ANGLES = [0, -3, 3]

def preprocess_for_ocr(img: Image.Image, rotate_angle: int) -> Image.Image:
    if rotate_angle != 0:
        img = img.rotate(rotate_angle, expand=True, fillcolor=(255, 255, 255))
    img = img.resize((img.width * 3, img.height * 3), Image.LANCZOS)
    return ImageEnhance.Contrast(ImageOps.grayscale(img)).enhance(1.5).convert("RGB")

async def process_folder(folder_path, log_callback, done_callback):
    folder, rows, success_count = Path(folder_path), [], 0
    files = sorted([f for f in folder.iterdir() if f.suffix.lower() in {".jpg", ".jpeg"}])
    
    if not files:
        log_callback("Tidak ada file foto di folder ini."); done_callback(); return

    log_callback(f"Memulai pemindaian {len(files)} file...\n" + "-"*40)
    start_time = time.time()
    scenarios = [("Kanan Atas", (0.65, 0.01, 0.98, 0.12), 0), ("Kanan Bawah", (0.85, 0.50, 1.00, 1.00), 90),
                 ("Kiri Atas", (0.01, 0.01, 0.15, 0.50), -90), ("Kiri Bawah", (0.01, 0.85, 0.40, 1.00), 180)]

    for idx, filepath in enumerate(files, 1):
        try:
            with Image.open(filepath) as raw_img:
                img = ImageOps.exif_transpose(raw_img).convert("RGB")
            new_name, is_found = "", False
            for name, box, base_angle in scenarios:
                if is_found: break
                crop_img = img.crop((int(img.width * box[0]), int(img.height * box[1]), int(img.width * box[2]), int(img.height * box[3])))
                for tilt in TILT_ANGLES:
                    text = " ".join([l.text for l in (await winocr.recognize_pil(preprocess_for_ocr(crop_img, base_angle+tilt), "en-US")).lines]).strip()
                    
                    # Regex baru yang mendeteksi 16 digit (awalan 35) atau persis 8 digit
                    match = re.search(r'(?<!\d)(35\d{14}|\d{8})(?!\d)', text.replace('O','0').replace('o','0').replace('I','1').replace('l','1').replace('S','5').replace(' ','').replace('-',''))
                    if match:
                        new_name, is_found = match.group(1), True; break

            if new_name:
                cand, c = folder / f"{new_name}{filepath.suffix.lower()}", 1
                while cand.exists(): cand, c = folder / f"{new_name}_{c}{filepath.suffix.lower()}", c + 1
                filepath.rename(cand)
                success_count += 1
                log_callback(f"[{idx}/{len(files)}] {filepath.name} ➔ {cand.name}")
            else:
                log_callback(f"[{idx}/{len(files)}] {filepath.name} ➔ GAGAL")
            rows.append({"file": filepath.name, "baru": cand.name if new_name else "", "status": "OK" if new_name else "GAGAL"})
        except Exception as e: log_callback(f"[{idx}] ERROR: {e}")

    total_time = time.time() - start_time
    with open(folder / "log_rename.csv", "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["file", "baru", "status"]); writer.writeheader(); writer.writerows(rows)

    log_callback("-" * 40 + f"\n SELESAI \nBerhasil: {success_count} | Gagal: {len(files)-success_count}")
    log_callback(f"Waktu Total: {int(total_time//60)}m {int(total_time%60)}s (Rata-rata: {total_time/len(files):.2f}s/file)")
    done_callback()

class PetaRenamerApp:
    def __init__(self, root):
        self.root, self.folder_path = root, ""
        self.root.title("Auto Rename Peta BPS"); self.root.geometry("600x500"); self.root.configure(padx=15, pady=15)
        
        frame = tk.Frame(root); frame.pack(fill=tk.X, pady=5)
        self.btn_folder = tk.Button(frame, text="Pilih Folder", command=self.pilih_folder, width=15)
        self.btn_folder.pack(side=tk.LEFT, padx=(0, 10))
        self.lbl_folder = tk.Label(frame, text="Belum ada folder terpilih", fg="gray")
        self.lbl_folder.pack(side=tk.LEFT)

        self.btn_mulai = tk.Button(root, text="MULAI RENAME", command=self.mulai_proses, state=tk.DISABLED, bg="#EF5C13", fg="white", font=("Arial", 10, "bold"), pady=5)
        self.btn_mulai.pack(fill=tk.X, pady=10)

        self.txt_log = scrolledtext.ScrolledText(root, width=70, height=20, bg="#F4F4F4")
        self.txt_log.pack(fill=tk.BOTH, expand=True)

    def tulis_log(self, pesan): self.root.after(0, lambda: [self.txt_log.insert(tk.END, pesan + "\n"), self.txt_log.see(tk.END)])
    def pilih_folder(self):
        if fd := filedialog.askdirectory(title="Pilih Folder Foto"):
            self.folder_path = fd; self.lbl_folder.config(text=f".../{Path(fd).name}", fg="black")
            self.btn_mulai.config(state=tk.NORMAL); self.txt_log.delete(1.0, tk.END); self.tulis_log(f"Target: {fd}")
    def mulai_proses(self):
        self.btn_mulai.config(state=tk.DISABLED, text="MEMPROSES..."); self.btn_folder.config(state=tk.DISABLED)
        threading.Thread(target=lambda: asyncio.run(process_folder(self.folder_path, self.tulis_log, lambda: self.root.after(0, lambda: [self.btn_mulai.config(state=tk.NORMAL, text="START RENAME"), self.btn_folder.config(state=tk.NORMAL)]))), daemon=True).start()

if __name__ == "__main__":
    app = tk.Tk(); PetaRenamerApp(app); app.mainloop()