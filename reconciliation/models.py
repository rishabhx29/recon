from django.db import models


class Organization(models.Model):
    # the X-Organization header carries this, not the display name
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=200)

    def __str__(self):
        return self.name


class InvestorEntity(models.Model):
    organization = models.ForeignKey(
        Organization, on_delete=models.CASCADE, related_name='investors'
    )
    # the legal entity name the bank puts in wire descriptions
    name = models.CharField(max_length=200)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['organization', 'name'], name='unique_investor_name_per_org'
            ),
        ]

    def __str__(self):
        return self.name
