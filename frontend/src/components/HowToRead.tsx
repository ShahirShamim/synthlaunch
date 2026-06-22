import { Accordion, AccordionContent, AccordionItem, AccordionTrigger } from "@/components/ui/accordion"

export interface Explainer {
  what: string
  read: string
  tells: string
}

// A consistent "How to read this chart" disclosure for a non-technical audience.
export function HowToRead({ explainer }: { explainer: Explainer }) {
  return (
    <Accordion className="w-full">
      <AccordionItem value="how" className="border-none">
        <AccordionTrigger className="py-2 text-sm text-muted-foreground hover:no-underline">
          How to read this chart
        </AccordionTrigger>
        <AccordionContent className="space-y-2 text-sm">
          <p>
            <span className="font-medium text-foreground">What you're looking at — </span>
            {explainer.what}
          </p>
          <p>
            <span className="font-medium text-foreground">How to read it — </span>
            {explainer.read}
          </p>
          <p>
            <span className="font-medium text-foreground">What it tells you — </span>
            {explainer.tells}
          </p>
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  )
}
