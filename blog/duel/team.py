"""ORM answers generated with Codex and verified by the official duel."""
from datetime import date

from django.db.models import Count

from blog.models import Author, Comment, Post


def q1():
    """Return published posts."""
    return Post.objects.filter(published=True)


def q2():
    """Return posts without a category."""
    return Post.objects.filter(category__isnull=True)


def q3():
    """Include both endpoints of the publication date interval."""
    return Post.objects.filter(
        published_at__range=(date(2026, 3, 1), date(2026, 5, 31))
    )


def q4():
    """Count comments in SQL before filtering."""
    return Post.objects.annotate(n_comments=Count("comments")).filter(
        n_comments__gt=2
    )


def q5():
    """Count each relation independently despite the joined rows."""
    return (
        Post.objects.filter(published=True)
        .annotate(
            n_comments=Count("comments", distinct=True),
            n_tags=Count("tags", distinct=True),
        )
        .order_by("-n_comments", "pk")[:3]
    )


def q6():
    """Traverse the author's one-to-one profile."""
    return Post.objects.filter(author__profile__country="Perú")


def q7():
    """Return comments through the post's category."""
    return Comment.objects.filter(post__category__name="Tecnología")


def q8():
    """Exclude authors having any published post, including mixed histories."""
    return Author.objects.exclude(posts__published=True)
