from django.db import models

class Organization(models.Model):
    
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=200)

    def __str__(self):
        return self.name
