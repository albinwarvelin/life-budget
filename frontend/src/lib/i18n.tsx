import { createContext, ReactNode, useContext, useMemo, useState } from "react";

export type Locale = "en" | "sv";

const translations = {
  en: {
    brand: "Life Budget", transactions: "Transactions", accounts: "Accounts", settings: "Settings",
    localWorkspace: "Local workspace", privateByDefault: "Private by default", yourMoney: "Your money, clearly",
    transactionSubtitle: "Record and review the movement of money across your accounts.", addTransaction: "Add transaction",
    currency: "Currency", allCurrencies: "All currencies", type: "Type", allTypes: "All types", expense: "Expense",
    expenses: "Expenses", income: "Income", reimbursement: "Reimbursement", reimbursements: "Reimbursements", transfer: "Transfer", transfers: "Transfers",
    records: "records", date: "Date", description: "Description", account: "Account", category: "Category", amount: "Amount", actions: "Actions",
    uncategorized: "Uncategorized", edit: "Edit", delete: "Delete", noTransactions: "No transactions yet", noTransactionsText: "Add your first transaction to start seeing your money clearly.",
    manualEntry: "Manual entry", editTransaction: "Edit transaction", addTransactionTitle: "Add transaction", close: "Close", cancel: "Cancel", saveChanges: "Save changes", saving: "Saving…",
    takenFromAccount: "Taken from the account.", optional: "Optional", merchant: "Merchant", notes: "Notes", whatFor: "What was this for?", amountPlaceholder: "0.00",
    accountsSubtitle: "Set up where your money lives before adding transactions.", newAccount: "New account", addAnAccount: "Add an account", accountName: "Account name", accountType: "Account type", institution: "Institution", bank: "Bank", cash: "Cash", broker: "Broker", other: "Other", connectedLocally: "Connected locally", yourAccounts: "Your accounts", noAccounts: "No accounts yet.", addAccount: "Add account",
    setupAccount: "Set up an account →", addAccountFirst: "Add an account first. Transactions must belong to an account with a known currency.",
    couldNotLoad: "Could not load data", backendHint: "Make sure the backend is running at http://localhost:8000.", loading: "Loading your data…",
    month: "Month", overview: "Overview", chooseMonth: "Choose month", total: "Total", byAccount: "By account", byCategory: "By category", monthlyActivity: "Monthly activity", noData: "No data for this period.",
    settingsSubtitle: "Choose how Life Budget speaks to you.", language: "Language", english: "English", swedish: "Swedish", languageSaved: "Language preference is saved locally.",
    manageCategories: "Manage categories and language →", attachment: "Attachment", attachFile: "Attach file or image", removeAttachment: "Remove attachment", attachmentHint: "Images, PDF, text files up to 10 MB.",
    unknownAccount: "Unknown account", unknownCategory: "Unknown category", deleteQuestion: "Delete this transaction?",
  },
  sv: {
    brand: "Life Budget", transactions: "Transaktioner", accounts: "Konton", settings: "Inställningar", localWorkspace: "Lokal arbetsyta", privateByDefault: "Privat som standard", yourMoney: "Dina pengar, tydligt", transactionSubtitle: "Registrera och granska pengarnas rörelser mellan dina konton.", addTransaction: "Lägg till transaktion", currency: "Valuta", allCurrencies: "Alla valutor", type: "Typ", allTypes: "Alla typer", expense: "Utgift", expenses: "Utgifter", income: "Inkomst", reimbursement: "Återbetalning", reimbursements: "Återbetalningar", transfer: "Överföring", transfers: "Överföringar", records: "poster", date: "Datum", description: "Beskrivning", account: "Konto", category: "Kategori", amount: "Belopp", actions: "Åtgärder", uncategorized: "Okategoriserad", edit: "Redigera", delete: "Ta bort", noTransactions: "Inga transaktioner ännu", noTransactionsText: "Lägg till din första transaktion för att se dina pengar tydligare.", manualEntry: "Manuell registrering", editTransaction: "Redigera transaktion", addTransactionTitle: "Lägg till transaktion", close: "Stäng", cancel: "Avbryt", saveChanges: "Spara ändringar", saving: "Sparar…", takenFromAccount: "Hämtas från kontot.", optional: "Valfritt", merchant: "Handlare", notes: "Anteckningar", whatFor: "Vad gällde detta?", amountPlaceholder: "0,00", accountsSubtitle: "Ställ in var dina pengar finns innan du lägger till transaktioner.", newAccount: "Nytt konto", addAnAccount: "Lägg till ett konto", accountName: "Kontonamn", accountType: "Kontotyp", institution: "Institut", bank: "Bank", cash: "Kontanter", broker: "Mäklare", other: "Annat", connectedLocally: "Anslutna lokalt", yourAccounts: "Dina konton", noAccounts: "Inga konton ännu.", addAccount: "Lägg till konto", setupAccount: "Ställ in ett konto →", addAccountFirst: "Lägg till ett konto först. Transaktioner måste tillhöra ett konto med en känd valuta.", couldNotLoad: "Kunde inte läsa in data", backendHint: "Kontrollera att backend körs på http://localhost:8000.", loading: "Läser in dina data…", month: "Månad", overview: "Översikt", chooseMonth: "Välj månad", total: "Totalt", byAccount: "Per konto", byCategory: "Per kategori", monthlyActivity: "Månadsaktivitet", noData: "Ingen data för denna period.", settingsSubtitle: "Välj hur Life Budget ska tala med dig.", language: "Språk", english: "Engelska", swedish: "Svenska", languageSaved: "Språkvalet sparas lokalt.", manageCategories: "Hantera kategorier och språk →", attachment: "Bilaga", attachFile: "Bifoga fil eller bild", removeAttachment: "Ta bort bilaga", attachmentHint: "Bilder, PDF och textfiler upp till 10 MB.", unknownAccount: "Okänt konto", unknownCategory: "Okänd kategori", deleteQuestion: "Ta bort den här transaktionen?",
  },
} as const;

type TranslationKey = keyof typeof translations.en;
type I18nValue = { locale: Locale; setLocale: (locale: Locale) => void; t: (key: TranslationKey) => string };
const I18nContext = createContext<I18nValue | null>(null);

// Keeping translation lookup as a pure function makes the locale contract
// testable without rendering the application.
export function translate(locale: Locale, key: TranslationKey) {
  return translations[locale][key];
}

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(() => (localStorage.getItem("life-budget-locale") as Locale) || "en");
  const setLocale = (next: Locale) => { setLocaleState(next); localStorage.setItem("life-budget-locale", next); };
  const value = useMemo(() => ({ locale, setLocale, t: (key: TranslationKey) => translate(locale, key) }), [locale]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n() {
  const context = useContext(I18nContext);
  if (!context) throw new Error("useI18n must be used inside I18nProvider");
  return context;
}

export const localeNames: Record<Locale, string> = { en: "English", sv: "Svenska" };
