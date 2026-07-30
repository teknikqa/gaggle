"""Constants for the gaggle integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "gaggle"

# Auth0 / AGL API
AGL_AUTH_HOST: Final = "https://secure.agl.com.au"
AGL_API_HOST: Final = "https://api.platform.agl.com.au"
# iOS app client_id — matches AGL mobile app 8.38.0-531 (documented 2026-04-30).
AGL_CLIENT_ID: Final = "2mDkNcC8gkDLL7FTT1ZxF5rrQHrLTHL3"
# Match the AGL mobile app client-flavor; AGL servers may reject unknown clients.
AGL_CLIENT_FLAVOR: Final = "app.iOS.public.8.38.0-531"
AGL_USER_AGENT: Final = "AGL/531 CFNetwork/3860.500.112 Darwin/25.4.0"

# Auth0 PKCE / OAuth2 redirect
AGL_AUTH0_CLIENT: Final = (
    "eyJuYW1lIjoiQXV0aDAuc3dpZnQiLCJ2ZXJzaW9uIjoiMi4xMi4wIiwiZW52Ijp7ImlPUyI6IjI2"
    "LjQiLCJzd2lmdCI6IjYueCJ9fQ"
)
AGL_REDIRECT_URI: Final = "https://secure.agl.com.au/ios/au.com.agl.mobile/callback"
AGL_OAUTH_SCOPE: Final = "openid profile email offline_access"
AGL_OAUTH_AUDIENCE: Final = "https://api.platform.agl.com.au/"

# Polling cadence. A basic gas meter's usage endpoint returns the current
# period's ESTIMATE (which AGL updates roughly daily) plus a window of
# already-billed past periods in ONE call — there is no per-day backfill
# loop here (unlike haggle's electricity coordinator, which fetches
# interval data day-by-day). 24h keeps the current-period estimate fresh
# without hammering AGL for data that barely changes.
SCAN_INTERVAL: Final = timedelta(hours=24)
# Retry cadence after a FAILED poll — a transient AGL error at poll time
# shouldn't cost a full day and look like "the poll never ran" (same
# self-healing pattern as the sibling electricity integration). Restored
# to SCAN_INTERVAL on the next success.
RETRY_INTERVAL_ON_ERROR: Final = timedelta(minutes=30)

# AGL BFF requires these headers on Hourly/Daily usage endpoints (HTTP 500 without them).
# Documented from AGL mobile app 8.38.0-531 — 2026-05-01. Confirmed required
# on the electricity Hourly/Daily endpoints; also sent on the confirmed real
# gas usage.basic.Gas call (Phase 0, 2026-07-30) alongside the rest of the
# default headers, though that endpoint hasn't been tested WITHOUT them to
# confirm they're strictly required there too — kept for consistency with
# the rest of the BFF.
AGL_ACCEPT_FEATURES: Final = (
    "AccountEnableCarbonNeutral, AccountEnableCarbonNeutralMessagingRemoval,"
    " AccountEnableConcessionMessaging, AccountEnableConsumerDataRight,"
    " AccountEnableDirectDebitSetup, AccountEnableHideTelcoNoChangeWarning,"
    " AccountEnableMessagingInfoItem, AccountEnableNativeAccountDeletion,"
    " AccountEnableTelcoDirectDebit, BillingEnableDirectDebitSetup,"
    " BillingEnableEnergyPaymentDirectDebit, BillingEnableEnergyViewPlan,"
    " BillingEnablePaymentArrangement, BillingEnableTransactionHistory,"
    " BillingEnableUpdatedPastBillsFlow, BillingEnableV3,"
    " DeeplinkEnableBpFuelOffer, DeeplinkEnableBpPulseOffer,"
    " DeeplinkEnableElectrifyNowLanding, DeeplinkEnableInAppSales,"
    " DeeplinkEnablePushNotificationPreferences, DeeplinkEnableTransactionHistory,"
    " ElectricityServiceHubEnableFinancialHardship, ElectricityServiceHubEnableMessaging,"
    " EnableAglAssistantRebrand, EnableHighBillProjectionTreatment,"
    " EnableInAppSales, EnableMobileSimActivationSetting, EnableServiceHub,"
    " EnableTelcoServiceHub, EnableUsageFromOverview, EnergyPlanEnableManageActions,"
    " EnergyServiceHubEnableBudgetTracker, EnergyServiceHubEnableElectricityUsageDisclaimer,"
    " EnergyServiceHubEnableHidingSettingsTitle, HelpCentreEnableArrangeYourMoveQuickLink,"
    " HelpCentreEnableDisconnectMessagingFaq, HelpCentreEnableSetupTwoFactorAuthentication,"
    " HelpEnableConsumerDataRight, HelpEnableFamilyDomesticViolenceSupport,"
    " HelpEnableTelcoFinancialHardshipLink, InAppSalesEnableElectrifyNow,"
    " InAppSalesEnablePeakEnergyRewards, InAppSalesEnableRewardsTile,"
    " InAppSalesEnableTelcoOffersSourceChange, LoginEnableAuth0HttpsCallbacks,"
    " LoginEnablePasskey, LoginEnablePasskeyButton, MessagingEnableUpdateSdk,"
    " OffersEnableOverviewAlertBanner, OffersEnableV3,"
    " OverviewAndAccountEnableSecurityCentre, OverviewAndViewPlanEnableNetflix,"
    " OverviewEnableHideTelcoCarbonNeutralLabel, OverviewEnableMessaging,"
    " OverviewEnableMultiOffers, OverviewEnableOffer, OverviewEnableV3,"
    " OverviewV3EnableSolarHealth, PushEnablePreferenceManagement,"
    " PushPreferencesEnableHasTelcoFlag, QuickTourEnable,"
    " ServiceHubEnableAccessVirtualCircuitId, ServiceHubEnableEnergyPlan,"
    " ServiceHubEnableMobileChangePlan, ServiceHubEnableMobileConfiguration,"
    " ServiceHubEnableNbnChangePlan, ServiceHubEnableNbnCostOfPlanDisclaimer,"
    " ServiceHubEnableUsageInsightSmartElectricity,"
    " ServiceHubEnableUsageInsightSmartElectricitySolar,"
    " TelcoServiceHubEnableMobileESimCopy, UsageEnableBattery,"
    " UsageEnableHistoricalMeterReads, UsageEnableMultiMeterRead,"
    " UsageEnableVirtualPowerPlant, UsageInsightEnableSolarRecommendation,"
    " VirtualPowerPlantEnableByobV3"
)
AGL_CLIENT_DEVICE: Final = "Apple-iPhone-iPhone14,7-iOS-26.4.2"  # documented 2026-05-01
# Screen scaling vector required by the BFF for usage chart rendering.
AGL_SCALING: Final = "36.514404_108.057_40.670903_120.357_0_0_0_0"

# Fuel-type value on a gas contract entry from /api/v3/overview
# (Contract.fuel_type). Real observed value, not a guess — see AGENTS.md
# "AGL API — Key Facts". gaggle is gas-only, so the config flow filters
# discovered contracts down to this value.
GAS_FUEL_TYPE: Final = "gasContract"

# Statistic ID suffixes — full ID is f"{DOMAIN}:{STAT_*}_{contract_number}"
STAT_CONSUMPTION: Final = "consumption"  # → gaggle:consumption_{contract}
STAT_COST: Final = "cost"  # → gaggle:cost_{contract}

# Gas usage unit — CONFIRMED MJ (Phase 0 capture, 2026-07-30):
# unitOfMeasurement/quantity fields throughout usage.basic.Gas all read
# "MJ". unit_class="energy" is required regardless of the unit string for
# the statistic to appear in the Energy dashboard's consumption picker
# (see AGENTS.md "Energy Dashboard Contract").
GAS_USAGE_UNIT: Final = "MJ"
# Plan rate-row type string for a per-unit gas usage rate. Confirmed real
# gas plans use tiered/block c/MJ rows ("First N MJ" / "Next N MJ" /
# "Thereafter") rather than one flat rate — see agl/parser.py::parse_plan
# and coordinator.py for how a single rate is picked from the tiers.
GAS_RATE_TYPE: Final = "c/MJ"

# Config-entry keys.
# CONF_EMAIL / CONF_PASSWORD are NOT used — auth is via refresh token.
CONF_REFRESH_TOKEN: Final = "refresh_token"  # ← it IS a token key
CONF_CONTRACT_NUMBER: Final = "contract_number"
CONF_ACCOUNT_NUMBER: Final = "account_number"
# SHA-256 hex of the leaf-cert SPKI captured at config-flow time. Empty string
# = no pin yet (older entries pre-PR4 / capture failed at install time).
CONF_PINNED_SPKI_AUTH: Final = "pinned_spki_auth"  # secure.agl.com.au
CONF_PINNED_SPKI_BFF: Final = "pinned_spki_bff"  # api.platform.agl.com.au

# Coordinator data attribute names — must match GaggleData field names exactly.
# Named generically ("usage"/"unit", not "mj") so a future unit change
# doesn't leave a misleadingly-named field behind.
DATA_CONSUMPTION_KWH: Final = "latest_cumulative_usage"  # cumulative total usage
DATA_CONSUMPTION_COST: Final = "latest_cumulative_cost_aud"  # cumulative total cost
DATA_CONSUMPTION_PERIOD: Final = (
    "consumption_period_usage"  # usage this bill period (estimate)
)
DATA_CONSUMPTION_PERIOD_COST: Final = (
    "consumption_period_cost_aud"  # cost this period (estimate)
)
DATA_PROJECTION_COST: Final = (
    "projection_cost_aud"  # AGL's own bill projection for this period
)
DATA_UNIT_RATE: Final = "unit_rate_aud_per_unit"  # AUD per unit of usage
DATA_SUPPLY_CHARGE: Final = "supply_charge_aud_per_day"  # AUD/day
