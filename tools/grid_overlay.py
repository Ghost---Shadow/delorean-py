"""Draw a labelled 10% grid over a reference so crop boxes can be read off by eye."""
import sys, cv2, numpy as np

def overlay(path, out, step=0.1, width=1400):
    im = cv2.imread(path)
    h, w = im.shape[:2]
    im = cv2.resize(im, (width, int(h * width / w)))
    h, w = im.shape[:2]
    n = int(round(1 / step))
    for i in range(n + 1):
        x, y = int(w * i * step), int(h * i * step)
        cv2.line(im, (x, 0), (x, h), (0, 255, 255), 1)
        cv2.line(im, (0, y), (w, y), (0, 255, 255), 1)
        cv2.putText(im, f"{i*step:.1f}", (x + 3, 16), 0, 0.45, (0, 0, 255), 1)
        cv2.putText(im, f"{i*step:.1f}", (3, y + 16), 0, 0.45, (0, 0, 255), 1)
    cv2.imwrite(out, im)

if __name__ == "__main__":
    overlay(sys.argv[1], sys.argv[2])
