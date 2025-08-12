from PIL import Image, ImageChops, ImageStat

def images_are_similar(p1: str, p2: str, tolerance=5) -> bool:
    with Image.open(p1).convert("RGB") as im1, Image.open(p2).convert("RGB") as im2:
        if im1.size != im2.size:
            return False
        diff = ImageChops.difference(im1, im2)
        stat = ImageStat.Stat(diff)
        mean_diff = sum(stat.mean) / len(stat.mean)
        print(f"📸 Mean pixel diff: {mean_diff}")
        return mean_diff <= tolerance
