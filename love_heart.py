import tkinter as tk
import random
import math
import time

def create_heart_window(x, y, text):
    win = tk.Toplevel()
    win.geometry(f"120x40+{x}+{y}")
    win.overrideredirect(True)
    win.attributes("-alpha", 0.9)
    tk.Label(win, text=text, font=("微软雅黑", 10), bg=random.choice(["#FF6B6B","#4ECDC4","#45B7D1","#96CEB4","#FFEAA7"])).pack()
    win.after(3000, win.destroy)

def heart_points(num, sw, sh):
    points = []
    cx, cy = sw//2, sh//2
    for i in range(num):
        t = i/num * 2*math.pi
        x = cx + 16*math.sin(t)**3 * 20
        y = cy - (13*math.cos(t)-5*math.cos(2*t)-2*math.cos(3*t)-math.cos(4*t)) * 20
        points.append((int(x), int(y)))
    return points

root = tk.Tk()
sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
root.withdraw()

texts = ["想你了","好好爱自己","多喝水","别熬夜","照顾好自己","天冷了多穿衣","按时吃饭","我想你","要开心","记得想我"]
for p in heart_points(100, sw, sh):
    create_heart_window(p[0], p[1], random.choice(texts))
    time.sleep(0.05)

for _ in range(sw//150 * sh//40 + 50):
    create_heart_window(random.randint(0, sw-120), random.randint(0, sh-40), random.choice(texts))
    time.sleep(0.02)

root.mainloop()
