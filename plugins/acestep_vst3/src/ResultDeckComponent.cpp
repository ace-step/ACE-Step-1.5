#include "ResultDeckComponent.h"

#include "V2Chrome.h"

namespace acestep::vst3
{
ResultDeckComponent::ResultDeckComponent()
{
    resultLabel_.setText("Take Select", juce::dontSendNotification);
    resultLabel_.setColour(juce::Label::textColourId, v2::kLabelMuted);
    comparePrimaryLabel_.setText("Compare A", juce::dontSendNotification);
    compareSecondaryLabel_.setText("Compare B", juce::dontSendNotification);
    comparePrimaryLabel_.setColour(juce::Label::textColourId, v2::kLabelMuted);
    compareSecondaryLabel_.setColour(juce::Label::textColourId, v2::kLabelMuted);
    summaryLabel_.setColour(juce::Label::textColourId, v2::kLabelPrimary);
    summaryLabel_.setJustificationType(juce::Justification::centredLeft);
    compareSummaryLabel_.setColour(juce::Label::textColourId, v2::kAccentMint);
    compareSummaryLabel_.setJustificationType(juce::Justification::centredLeft);
    addAndMakeVisible(resultLabel_);
    addAndMakeVisible(resultSelector_);
    addAndMakeVisible(summaryLabel_);
    addAndMakeVisible(comparePrimaryLabel_);
    addAndMakeVisible(compareSecondaryLabel_);
    addAndMakeVisible(comparePrimarySelector_);
    addAndMakeVisible(compareSecondarySelector_);
    addAndMakeVisible(cueCompareAButton_);
    addAndMakeVisible(cueCompareBButton_);
    addAndMakeVisible(toggleCompareButton_);
    addAndMakeVisible(compareSummaryLabel_);
}

void ResultDeckComponent::paint(juce::Graphics& g)
{
    v2::drawModule(g, getLocalBounds(), "Result Deck", v2::kAccentBlue);
}

void ResultDeckComponent::resized()
{
    auto area = getLocalBounds().reduced(18);
    area.removeFromTop(24);
    resultLabel_.setBounds(area.removeFromTop(18));
    resultSelector_.setBounds(area.removeFromTop(32));
    area.removeFromTop(10);
    summaryLabel_.setBounds(area.removeFromTop(58));
    area.removeFromTop(8);

    auto compareRow = area.removeFromTop(26);
    comparePrimaryLabel_.setBounds(compareRow.removeFromLeft(72));
    comparePrimarySelector_.setBounds(compareRow.removeFromLeft(160));
    compareRow.removeFromLeft(8);
    cueCompareAButton_.setBounds(compareRow.removeFromLeft(70));
    compareRow.removeFromLeft(12);
    compareSecondaryLabel_.setBounds(compareRow.removeFromLeft(72));
    compareSecondarySelector_.setBounds(compareRow.removeFromLeft(160));
    compareRow.removeFromLeft(8);
    cueCompareBButton_.setBounds(compareRow.removeFromLeft(70));
    compareRow.removeFromLeft(12);
    toggleCompareButton_.setBounds(compareRow.removeFromLeft(104));

    area.removeFromTop(8);
    compareSummaryLabel_.setBounds(area.removeFromTop(22));
}

juce::ComboBox& ResultDeckComponent::resultSelector() noexcept { return resultSelector_; }
juce::ComboBox& ResultDeckComponent::comparePrimarySelector() noexcept
{
    return comparePrimarySelector_;
}
juce::ComboBox& ResultDeckComponent::compareSecondarySelector() noexcept
{
    return compareSecondarySelector_;
}
juce::TextButton& ResultDeckComponent::cueCompareAButton() noexcept { return cueCompareAButton_; }
juce::TextButton& ResultDeckComponent::cueCompareBButton() noexcept { return cueCompareBButton_; }
juce::TextButton& ResultDeckComponent::toggleCompareButton() noexcept
{
    return toggleCompareButton_;
}

void ResultDeckComponent::setTakeSummary(const juce::String& title, const juce::String& detail)
{
    summaryLabel_.setText(title + "\n" + detail, juce::dontSendNotification);
}

void ResultDeckComponent::setCompareSummary(const juce::String& summary)
{
    compareSummaryLabel_.setText(summary, juce::dontSendNotification);
}
}  // namespace acestep::vst3
