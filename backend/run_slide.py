import sys
from app.db import SessionLocal
from app.models.slide import Slide
from app.models.slideshow import Slideshow
from app.services.generate_with_retry import generate_with_retry
idx = int(sys.argv[1]); ss_prefix = sys.argv[2] if len(sys.argv) > 2 else 'e3fbf713'
db = SessionLocal()
ss = db.query(Slideshow).filter(Slideshow.id.like(ss_prefix + '%')).one()
slide = db.query(Slide).filter(Slide.slideshow_id == ss.id, Slide.slide_index == idx).one()
res = generate_with_retry(db, ss, quality_mode="fast", slide=slide, max_retries=1,
                          text_strategy="reuse_original")
if hasattr(res, "error"):
    print(f"SLIDE {idx}: STAGE ERROR {res.error[:160]}")
else:
    for i, att in enumerate(res.attempts):
        for c in att.candidates:
            qa = c.quality_assessment
            print(f"SLIDE {idx} attempt{i} {c.generated_image.id[:8]} {c.generated_image.provider} "
                  f"score={qa.overall_confidence_score:.3f} accepted={qa.accepted}")
    w = res.winner
    print(f"SLIDE {idx} WINNER {w.generated_image.id[:8] if w else 'NONE'}")
    if w: print(f"  generated: {w.generated_image.file_path}")
    if res.final_output: print(f"  final    : {res.final_output.file_path}")
db.close()
