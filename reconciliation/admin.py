from django.contrib import admin

from .models import (
    BankTransaction,
    CapitalCall,
    InvestorEntity,
    LineItem,
    Match,
    Organization,
)

admin.site.register(Organization)
admin.site.register(InvestorEntity)
admin.site.register(CapitalCall)
admin.site.register(LineItem)
admin.site.register(BankTransaction)
admin.site.register(Match)
